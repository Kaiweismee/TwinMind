"""討論插話流程：儲存訊息、選擇回覆對象、產生回應與備援。"""

from __future__ import annotations

from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any
import os
import random
import time

from fastapi import HTTPException

from web.core.dependencies import _enforce_session_access, _profile_for_user, _resolve_top_k
from web.repositories import chat_store
from web.conversations import discussion
from web.core.runtime import _RECOMMEND_POOL, _log
from web.schemas.requests import SendMessageRequest
from web.services.ai import _discussion_client
from web.services.turns import _turn_state


def send_message(
    session_id: int,
    body: SendMessageRequest,
    *,
    x_session_owner: str | None,
    user: dict[str, Any],
):
    """選填插話：有內容時會觸發新一輪辯論與結論。"""
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="插話內容不可為空")

    _enforce_session_access(
        session_id,
        x_session_owner=x_session_owner,
        user=user,
    )
    session = chat_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="找不到聊天室")

    guest_id = None

    requested_reply_to = (body.reply_to or "all").strip() or "all"
    profile = _profile_for_user(user)
    members = session.get("members") or []
    reply_to = requested_reply_to

    if requested_reply_to not in ("all", "user_twin"):
        by_slug: dict[str, dict[str, Any]] = {}
        by_name: dict[str, dict[str, Any]] = {}
        for m in members:
            slug = (m.get("person_slug") or m.get("slug") or "").strip()
            name = (m.get("name_zh") or "").strip()
            if slug:
                by_slug[slug] = m
            if name:
                by_name[name] = m
        if requested_reply_to not in by_slug:
            alias_hit = by_name.get(requested_reply_to)
            if alias_hit:
                reply_to = (alias_hit.get("person_slug") or alias_hit.get("slug") or "").strip() or "all"
            elif members:
                fallback_slug = (
                    members[0].get("person_slug")
                    or members[0].get("slug")
                    or "all"
                )
                reply_to = str(fallback_slug).strip() or "all"
                _log.warning(
                    "session %s reply target '%s' not found; fallback to '%s'",
                    session_id,
                    requested_reply_to,
                    reply_to,
                )
            else:
                reply_to = "all"

    meta: dict[str, str] = {
        "reply_to": reply_to,
        "requested_reply_to": requested_reply_to,
    }

    user_msg = chat_store.add_message(
        session_id, "user", content, guest_id=guest_id, sources=meta
    )
    user_msg["reply_to"] = reply_to
    user_msg["requested_reply_to"] = requested_reply_to
    topic = session.get("topic") or session.get("title") or "討論"
    replies: list[dict[str, Any]] = []
    speaking_order: list[dict[str, Any]] = []
    follow_up: str | None = None
    follow_up_error: str | None = None

    # 凡能進入討論室插話者，皆可觸發名人回覆（不限房主）
    can_run = bool(members)

    target_member: dict[str, Any] | None = None
    target_slug = reply_to
    if can_run and reply_to not in ("all", "user_twin"):
        for m in members:
            m_slug = (m.get("person_slug") or m.get("slug") or "").strip()
            if m_slug == reply_to:
                target_member = m
                target_slug = m_slug
                break
        if not target_member and members:
            target_member = members[0]
            target_slug = (
                (target_member.get("person_slug") or target_member.get("slug") or "").strip()
                or "all"
            )
            reply_to = target_slug

    def _fallback_direct_reply() -> dict[str, Any] | None:
        if target_slug in ("all", "user_twin"):
            return None
        member = target_member
        if not member:
            return None
        name_zh = member.get("name_zh") or target_slug
        user_text = (content or "").strip()
        fallback_text = ""
        if llm_client:
            try:
                quick_system = (
                    f"你是{name_zh}。請直接回覆使用者問題，語氣自然、具體，"
                    "使用繁體中文，2-4 句，不要用『我會先回答你』這種前言。"
                )
                quick_user = (
                    f"討論主題：{topic}\n"
                    f"使用者剛剛問：{user_text or '（未提供）'}\n"
                    "請直接給出你的觀點與一個具體建議。"
                )
                resp = llm_client.chat.completions.create(
                    model=llm_model,
                    messages=[
                        {"role": "system", "content": quick_system},
                        {"role": "user", "content": quick_user},
                    ],
                    temperature=0.55,
                    max_tokens=220,
                )
                fallback_text = (resp.choices[0].message.content or "").strip()
            except Exception:
                fallback_text = ""
        if not fallback_text:
            if user_text:
                fallback_text = (
                    f"你提到「{user_text}」這點很關鍵。以「{topic}」來看，"
                    f"{name_zh} 的建議是先把問題拆成可量化指標，先做一個小型驗證，"
                    "再依結果決定是否全面推進。"
                )
            else:
                fallback_text = (
                    f"針對「{topic}」，我建議先聚焦在最能影響決策品質的核心指標，"
                    "用小步快跑的方式驗證，再逐步擴大。"
                )
        packed = {
            "sources": [],
            "segments": [],
            "phase": "debate",
            "direct_reply": True,
            "reply_to": target_slug,
        }
        msg = chat_store.add_message(
            session_id,
            target_slug,
            fallback_text,
            person_slug=target_slug,
            sources=packed,
            phase="debate",
            content_segments=[],
        )
        return {
            **msg,
            "person_slug": target_slug,
            "person_name_zh": name_zh,
            "avatar_url": member.get("avatar_url") or "",
            "phase": "debate",
            "sources": [],
            "content_segments": [],
            "direct_reply": True,
            "reply_to": target_slug,
        }

    llm_client = None
    llm_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    single_follow_up_timeout_sec = float(
        os.getenv("CHAT_SINGLE_FOLLOW_UP_TIMEOUT_SEC", "8")
    )
    round_follow_up_timeout_sec = float(
        os.getenv("CHAT_ROUND_FOLLOW_UP_TIMEOUT_SEC", "120")
    )
    round_member_timeout_sec = float(
        os.getenv("CHAT_ROUND_MEMBER_TIMEOUT_SEC", "12")
    )
    round_soft_timeout_sec = float(
        os.getenv("CHAT_ROUND_SOFT_TIMEOUT_SEC", "45")
    )
    if can_run:
        try:
            llm_client, llm_model = _discussion_client()
            merged_brief = (session.get("context_brief") or "").strip() or None
            common = dict(
                session_id=session_id,
                members=members,
                topic=topic,
                user_name=profile.get("display_name") or "你",
                twin_context=profile.get("twin_context") or "",
                client=llm_client,
                model=llm_model,
                top_k=_resolve_top_k(body.top_k),
                discussion_brief=merged_brief,
                user_avatar_url=profile.get("avatar_url") or "",
                user_id=profile.get("id"),
            )
            if reply_to == "all":
                ordered_members = [
                    m
                    for m in members
                    if (m.get("person_slug") or m.get("slug") or "").strip()
                ]
                random.shuffle(ordered_members)
                round_started = time.monotonic()
                for m in ordered_members:
                    slug = (m.get("person_slug") or m.get("slug") or "").strip()
                    if not slug:
                        continue
                    speaking_order.append(
                        {
                            "person_slug": slug,
                            "name_zh": m.get("name_zh") or slug,
                            "avatar_url": m.get("avatar_url") or "",
                            "kind": "celeb",
                            "topic_fit_score": m.get("topic_fit_score"),
                        }
                    )
                    elapsed = time.monotonic() - round_started
                    if replies and elapsed >= round_soft_timeout_sec:
                        break
                    remaining = round_follow_up_timeout_sec - elapsed
                    if remaining <= 1:
                        break
                    one_timeout = max(1.0, min(round_member_timeout_sec, remaining))
                    try:
                        fut = _RECOMMEND_POOL.submit(
                            discussion.run_direct_reply,
                            **common,
                            target=slug,
                        )
                        one = fut.result(timeout=one_timeout)
                        if one:
                            one["interjection_index"] = len(replies) + 1
                            replies.append(one)
                    except FuturesTimeout:
                        _log.warning(
                            "session %s member %s interjection timed out after %.1fs",
                            session_id,
                            slug,
                            one_timeout,
                        )
                        continue
                    except Exception as exc:
                        _log.warning(
                            "session %s member %s interjection failed: %s",
                            session_id,
                            slug,
                            exc,
                        )
                        continue
                total = len(replies)
                for msg in replies:
                    msg["interjection_total"] = total
                if not replies:
                    follow_up_error = "本輪名人回覆逾時，請再試一次"
                follow_up = "round"
            else:
                fut = _RECOMMEND_POOL.submit(
                    discussion.run_direct_reply,
                    **common,
                    target=target_slug,
                )
                one = fut.result(timeout=single_follow_up_timeout_sec)
                if one:
                    replies.append(one)
                else:
                    fb = _fallback_direct_reply()
                    if fb:
                        replies.append(fb)
                follow_up = "single"
        except FuturesTimeout:
            timeout_used = (
                round_follow_up_timeout_sec if reply_to == "all" else single_follow_up_timeout_sec
            )
            follow_up_error = f"名人回覆逾時（>{int(timeout_used)} 秒）"
            if reply_to not in ("all", "user_twin"):
                fb = _fallback_direct_reply()
                if fb:
                    replies.append(fb)
                    follow_up_error = None
                    follow_up = "single"
        except HTTPException as exc:
            if exc.status_code not in (503, 500):
                raise
            follow_up_error = str(exc.detail)
            if reply_to not in ("all", "user_twin"):
                fb = _fallback_direct_reply()
                if fb:
                    replies.append(fb)
                    follow_up_error = None
                    follow_up = "single"
        except Exception as exc:
            follow_up_error = str(exc)
            if reply_to not in ("all", "user_twin"):
                fb = _fallback_direct_reply()
                if fb:
                    replies.append(fb)
                    follow_up_error = None
                    follow_up = "single"

    # 圖譜由前端在「思考中」以 live=1 更新；插話批次完成後不在此強制 LLM 覆寫
    insights_payload: dict[str, Any] | None = None

    try:
        state = _turn_state(session_id, profile=profile)
        result = {
            "user_message": user_msg,
            "content": content,
            "reply_to": reply_to,
            "requested_reply_to": requested_reply_to,
            "replies": replies,
            "speaking_order": speaking_order if reply_to == "all" else [],
            "follow_up": follow_up,
            "follow_up_error": follow_up_error,
            "insights": insights_payload,
            "awaiting_turn": not state["done"],
            "next_label": state["next_label"],
            "guest_id": guest_id,
        }
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
