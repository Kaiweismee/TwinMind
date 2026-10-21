"""
多人討論：一次一則發言；名人回覆須在句尾標註 [1][2] 對應參考資料。
"""

from __future__ import annotations

import os
import random
import re
from dataclasses import dataclass
from typing import Any

from search import format_context, search_chunks  # type: ignore

import chat_store

CITE_RE = re.compile(
    r"([^[\]【】]+?)(?:\[(?:(\d+)|推論)\]|【(?:(\d+)|推論)】)"
)


def _normalize_cite_markers(text: str) -> str:
    """將全形【1】【推論】統一成半形，方便解析與前端一致。"""
    t = re.sub(r"【(\d+)】", r"[\1]", text or "")
    return t.replace("【推論】", "[推論]")


@dataclass
class TurnSpec:
    kind: str  # user_twin | celeb | conclusion
    phase: str  # opening | debate | conclusion
    member: dict[str, Any] | None = None


def _format_transcript(
    messages: list[dict[str, Any]],
    user_name: str,
    *,
    exclude_roles: set[str] | None = None,
) -> str:
    exclude_roles = exclude_roles or set()
    lines: list[str] = []
    for m in messages:
        role = m.get("role")
        if role in exclude_roles:
            continue
        if role == "user":
            lines.append(f"{user_name}：{m['content']}")
        elif role == "user_twin":
            lines.append(f"{user_name}（分身）：{m['content']}")
        elif role == "conclusion":
            continue
        else:
            name = m.get("person_name_zh") or role
            lines.append(f"{name}：{m['content']}")
    return "\n".join(lines)


def _sources_payload(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in results:
        text = r.get("content") or ""
        if len(text) > 2800:
            text = text[:2800] + "…"
        out.append({
            "chunk_id": int(r["chunk_id"]),
            "similarity": round(float(r["similarity"]), 4),
            "title": r.get("title"),
            "source_type": r.get("source_type"),
            "source_url": r.get("source_url"),
            "content": text,
        })
    return out


def _pack_sources(sources: list[dict[str, Any]], segments: list[dict[str, Any]]) -> Any:
    if not segments:
        return sources
    return {"sources": sources, "segments": segments}


def _unpack_sources(raw: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if isinstance(raw, dict) and "sources" in raw:
        return list(raw.get("sources") or []), list(raw.get("segments") or [])
    if isinstance(raw, list):
        return raw, []
    return [], []


def parse_cited_reply(raw: str, sources: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """
    解析「……可能被取代[2]，但這也……[1]」→ 顯示文字 + 逐句引用。
    source_refs 為 1-based，對應本則訊息的 sources 列表。
    """
    text = _normalize_cite_markers((raw or "").strip())
    if not text:
        return "", []

    segments: list[dict[str, Any]] = []
    last = 0
    display_parts: list[str] = []

    for m in CITE_RE.finditer(text):
        before = text[last : m.start()].strip()
        if before:
            display_parts.append(before)
            segments.append({
                "text": before,
                "source_refs": [],
                "chunk_ids": [],
                "inference": True,
            })

        clause = m.group(1).strip()
        ref = m.group(2) or m.group(3)
        if not clause:
            last = m.end()
            continue

        display_parts.append(clause)
        if ref:
            idx = int(ref)
            chunk_ids: list[int] = []
            if 1 <= idx <= len(sources):
                chunk_ids = [int(sources[idx - 1]["chunk_id"])]
            segments.append({
                "text": clause,
                "source_refs": [idx],
                "chunk_ids": chunk_ids,
                "inference": False,
            })
        else:
            segments.append({
                "text": clause,
                "source_refs": [],
                "chunk_ids": [],
                "inference": True,
            })
        last = m.end()

    tail = text[last:].strip()
    if tail:
        display_parts.append(tail)
        segments.append({
            "text": tail,
            "source_refs": [],
            "chunk_ids": [],
            "inference": True,
        })

    if not segments:
        return text, [{
            "text": text,
            "source_refs": [],
            "chunk_ids": [],
            "inference": True,
        }]

    display = "".join(display_parts) if display_parts else text
    return display, segments


def _rag_context(person_slug: str, query: str, top_k: int) -> tuple[str, list[int], list[dict]]:
    results = search_chunks(query, person_slug=person_slug, top_k=top_k)
    context = format_context(results)
    if not context.strip():
        context = "（知識庫未檢索到相關資料）"
    chunk_ids = [int(r["chunk_id"]) for r in results]
    return context, chunk_ids, _sources_payload(results)


def _append_session_context(
    context: str,
    chunk_ids: list[int],
    sources: list[dict],
    *,
    user_id: int | None,
    session_id: int,
    query: str,
    top_k: int,
) -> tuple[str, list[int], list[dict]]:
    if not user_id or not session_id:
        return context, chunk_ids, sources
    import user_rag  # noqa: WPS433

    sess_ctx, sess_ids, sess_src = user_rag.search_session_context(
        user_id, session_id, query, top_k=min(6, top_k)
    )
    if not sess_ctx.strip():
        return context, chunk_ids, sources
    merged = (
        f"【房主提供的參考資料】\n{sess_ctx}\n\n【你的參考資料】\n{context}"
        if context.strip() and "未檢索到" not in context
        else f"【房主提供的參考資料】\n{sess_ctx}"
    )
    return merged, chunk_ids + sess_ids, sources + sess_src


def _llm(client: Any, model: str, system: str, user: str, temperature: float = 0.7) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    return (resp.choices[0].message.content or "").strip()


def _discussion_brief(topic: str, extra: str = "") -> str:
    if extra.strip():
        return extra.strip()
    return f"我們要討論的主題是：{topic}"


_CITE_RULE = (
    "【引用規則】你的發言會附編號參考資料，請用半形方括號 [1][2]（勿用【1】）。"
    "每一句或每一小段論述結尾，必須標註其依據：有資料則標 [編號]（如 ……可能被取代[2]）；"
    "若為推論或資料未提及則標 [推論]。不可在未標註的情況下寫出似曾來自資料的具體說法。"
)


def _member_debate_rounds(m: dict[str, Any]) -> int:
    dr = m.get("debate_rounds")
    if dr is not None:
        return max(0, min(6, int(dr)))
    from topic_fit import debate_rounds_from_fit

    return debate_rounds_from_fit(int(m.get("topic_fit_score") or 50))


def _fit_engagement_hint(topic_fit_score: int | None, phase: str) -> str:
    """依契合度要求發言深度（高契合多講、低契合少講）。"""
    score = 50 if topic_fit_score is None else int(topic_fit_score)
    if phase == "opening":
        if score >= 78:
            return (
                "【契合度：高】你是本主題的核心與會者，請充分展開立場、"
                "引用資料中的具體內容，並點出 2～3 個關鍵論點。"
            )
        if score >= 52:
            return "【契合度：中】請提出與主題相關的觀點，並簡要說明理由。"
        return "【契合度：低】簡短開場即可，避免過度延伸與主題無關的內容。"
    if score >= 78:
        return (
            "【契合度：高】請深入辯論：回應先前發言、提出反駁或補充例證，"
            "盡量引用資料；你是本輪應發言最多的專家之一。"
        )
    if score >= 52:
        return "【契合度：中】請回應他人觀點並補充你的看法，保持聚焦主題。"
    return "【契合度：低】簡短回應即可，勿長篇發揮。"


def _rag_top_k_for_fit(topic_fit_score: int | None, base: int) -> int:
    score = 50 if topic_fit_score is None else int(topic_fit_score)
    if score >= 78:
        return min(base + 8, 24)
    if score >= 52:
        return min(base + 4, 16)
    return max(4, base - 2)


def _members_by_fit(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        members,
        key=lambda x: (
            -(x.get("topic_fit_score") if x.get("topic_fit_score") is not None else 50),
            x.get("sort_order", 0),
        ),
    )


def build_turn_queue(
    members: list[dict[str, Any]],
    *,
    include_user_twin: bool = True,
    include_debate: bool = True,
    include_conclusion: bool = True,
) -> list[TurnSpec]:
    """開場人人有份；辯論至少 3 輪、高契合最多 4 輪，高契合先發言。"""
    queue: list[TurnSpec] = []
    ordered = _members_by_fit(members)
    if include_user_twin:
        queue.append(TurnSpec("user_twin", "opening", None))
    for m in ordered:
        queue.append(TurnSpec("celeb", "opening", m))
    if include_debate and len(members) >= 1:
        min_global = int(os.getenv("CHAT_MIN_DEBATE_ROUNDS", "3"))
        max_rounds = max((_member_debate_rounds(m) for m in members), default=0)
        max_rounds = max(max_rounds, min_global)
        for round_i in range(max_rounds):
            for m in ordered:
                if round_i < _member_debate_rounds(m):
                    queue.append(TurnSpec("celeb", "debate", m))
        if include_user_twin:
            queue.append(TurnSpec("user_twin", "debate", None))
    if include_conclusion:
        queue.append(TurnSpec("conclusion", "conclusion", None))
    return queue


def _assistant_turn_count(messages: list[dict[str, Any]]) -> int:
    n = 0
    for m in messages:
        if m.get("role") in ("user", "conclusion"):
            continue
        n += 1
    return n


def get_next_turn(
    messages: list[dict[str, Any]],
    members: list[dict[str, Any]],
    *,
    include_user_twin: bool = True,
) -> TurnSpec | None:
    if any(m.get("role") == "conclusion" for m in messages):
        return None
    queue = build_turn_queue(members, include_user_twin=include_user_twin)
    idx = _assistant_turn_count(messages)
    if idx >= len(queue):
        return None
    return queue[idx]


def peek_next_turn_label(
    messages: list[dict[str, Any]],
    members: list[dict[str, Any]],
    user_name: str,
    *,
    include_user_twin: bool = True,
) -> str | None:
    speaker = peek_next_speaker(
        messages, members, user_name, include_user_twin=include_user_twin
    )
    if not speaker:
        return None
    if speaker["kind"] == "conclusion":
        return "產出討論結論"
    if speaker["kind"] == "user_twin":
        return f"請 {user_name}（分身）發言"
    if speaker["kind"] == "celeb":
        phase_zh = "開場" if speaker.get("phase") == "opening" else "回應"
        return f"請 {speaker['name_zh']} {phase_zh}"
    return "下一位發言"


def peek_next_speaker(
    messages: list[dict[str, Any]],
    members: list[dict[str, Any]],
    user_name: str,
    *,
    user_avatar_url: str = "",
    include_user_twin: bool = True,
) -> dict[str, Any] | None:
    spec = get_next_turn(messages, members, include_user_twin=include_user_twin)
    if not spec:
        return None
    if spec.kind == "conclusion":
        return {
            "kind": "conclusion",
            "name_zh": "討論結論",
            "person_slug": None,
            "avatar_url": None,
            "phase": "conclusion",
        }
    if spec.kind == "user_twin":
        return {
            "kind": "user_twin",
            "name_zh": f"{user_name}（分身）",
            "person_slug": None,
            "avatar_url": user_avatar_url,
            "phase": spec.phase,
        }
    if spec.member:
        m = spec.member
        return {
            "kind": "celeb",
            "name_zh": m["name_zh"],
            "person_slug": m["person_slug"],
            "avatar_url": m.get("avatar_url") or "",
            "phase": spec.phase,
        }
    return None


def _format_user_note(
    content: str,
    reply_to: str | None,
    members: list[dict[str, Any]],
    user_name: str,
) -> str:
    text = (content or "").strip()
    if not text:
        return ""
    target = (reply_to or "all").strip() or "all"
    if target == "all":
        return text
    if target == "user_twin":
        return f"（指定對象：{user_name}的分身）{text}"
    for m in members:
        slug = m.get("person_slug") or ""
        if slug == target:
            name = m.get("name_zh") or slug
            return f"（指定對象：{name}）{text}"
    return text


def _latest_user_note(
    messages: list[dict[str, Any]],
    members: list[dict[str, Any]],
    user_name: str,
) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return _format_user_note(
                str(m.get("content") or ""),
                m.get("reply_to"),
                members,
                user_name,
            )
    return ""


def _reply_user_twin(
    client: Any,
    model: str,
    *,
    user_name: str,
    topic: str,
    twin_context: str,
    discussion_brief: str,
    history_text: str,
    phase: str,
    user_id: int | None = None,
    session_id: int | None = None,
    top_k: int = 8,
) -> tuple[str, list[int], list[dict[str, Any]]]:
    phase_hint = "開場" if phase == "opening" else "回應討論"
    user_rag_context = ""
    chunk_ids: list[int] = []
    sources: list[dict[str, Any]] = []
    if user_id:
        rag_q = f"{topic} {discussion_brief} {history_text[-500:]}"
        user_rag_context, chunk_ids, sources = _user_rag_context(user_id, rag_q, top_k)
        if session_id:
            import user_rag  # noqa: WPS433

            sess_ctx, sess_ids, sess_src = user_rag.search_session_context(
                user_id, session_id, rag_q, top_k=min(6, top_k)
            )
            if sess_ctx.strip():
                user_rag_context = (
                    f"{sess_ctx}\n\n{user_rag_context}"
                    if user_rag_context.strip()
                    else sess_ctx
                )
                chunk_ids = chunk_ids + sess_ids
                sources = sources + sess_src

    cite_rule = (
        "【引用規則】若依據【你的私人資料】發言，句尾標 [1][2]…；"
        "推論或未提及則標 [推論]。"
    )
    twin_cross = (
        "必須具體回應【目前討論】中名人的觀點（點名），並結合【你的私人資料】補充事實；"
        "不可忽略他人已說的話。"
        if phase != "opening"
        else "開場可簡述立場；若討論中已有名人發言，須點名回應。"
    )
    system = (
        f"你是{user_name}的數位分身，主題「{topic}」，這是{phase_hint}。"
        f"{twin_context}\n"
        f"{twin_cross}\n"
        f"{cite_rule if user_id else ''}\n"
        "繁體中文，開場約 120～180 字；辯論回應約 140～200 字，需回應名人觀點。"
    )
    user = (
        f"【你的私人資料（使用者曾與分身分享）】\n{user_rag_context}\n\n"
        f"【議題】\n{discussion_brief}\n\n"
        f"【目前討論】\n{history_text or '（無）'}\n\n"
        f"請以{user_name}的分身身份發言，並與契合度高的名人同樣積極參與。"
    )
    text = _llm(client, model, system, user, temperature=0.78)
    return text, chunk_ids, sources


def _user_rag_context(user_id: int, query: str, top_k: int) -> tuple[str, list[int], list[dict[str, Any]]]:
    import user_rag  # noqa: WPS433

    return user_rag.search_user_context(user_id, query, top_k=top_k)


def _cross_talk_rules(phase: str, prior_in_round: list[dict[str, str]]) -> str:
    """要求名人依先前發言與參考資料交叉討論。"""
    if prior_in_round:
        names = "、".join(dict.fromkeys(r["name"] for r in prior_in_round if r.get("name")))
        return (
            f"必須直接回應【本輪已發言】的 {names}：指出你同意、反駁或補充的具體觀點，"
            "並用【你的參考資料】補充可查證的事實（句尾 [編號]），推測標 [推論]。"
            "不可自說自話、不可只打招呼。"
        )
    if phase == "opening":
        return (
            "開場須表明立場；若【先前討論】已有他人發言，必須點名回應。"
            "事實須來自【你的參考資料】標 [編號]，無依據則標 [推論]。"
        )
    return (
        "必須承接【先前討論】已出現的觀點，點名至少一位與會者再延伸；"
        "事實來自【你的參考資料】標 [編號]，否則標 [推論]。"
    )


def _length_hint_for_fit(topic_fit_score: int | None, phase: str) -> str:
    score = 50 if topic_fit_score is None else int(topic_fit_score)
    if phase == "opening":
        if score >= 78:
            return "約 160～240 字，務必深入表態"
        if score >= 52:
            return "約 110～170 字"
        return "約 60～95 字，簡短開場即可"
    if score >= 78:
        return "約 180～280 字，深入延伸、反駁與舉例"
    if score >= 52:
        return "約 120～190 字"
    return "約 65～100 字，簡短回應即可"


def _reply_celeb(
    client: Any,
    model: str,
    *,
    name_zh: str,
    topic: str,
    discussion_brief: str,
    history_text: str,
    context: str,
    phase: str,
    prior_in_round: list[dict[str, str]],
    topic_fit_score: int | None = None,
    direct_address: bool = False,
) -> str:
    others = ""
    if prior_in_round:
        others = "\n【本輪已發言】\n" + "\n".join(
            f"{r['name']}：{r['content']}" for r in prior_in_round
        )
    if direct_address:
        phase_hint = "回應使用者對你的提問"
    else:
        phase_hint = "開場" if phase == "opening" else "交叉回應"
    length_hint = _length_hint_for_fit(topic_fit_score, phase)
    engagement = _fit_engagement_hint(topic_fit_score, phase)
    score = 50 if topic_fit_score is None else int(topic_fit_score)
    temp = 0.72 if phase == "opening" else 0.78
    if score >= 78:
        temp = min(0.85, temp + 0.06)
    cross_talk = _cross_talk_rules(phase, prior_in_round)
    no_repeat = (
        "【避免重複】勿再說「大家好我是…」等開場寒暄；"
        "辯論輪次須回應他人新觀點或提出新例證，禁止複述自己上一則的相同段落。"
    )
    system = (
        f"你是{name_zh}的數位分身，主題「{topic}」，這是{phase_hint}。"
        f"{engagement}\n"
        f"{cross_talk}\n"
        f"{no_repeat}\n"
        f"{_CITE_RULE}\n"
        "只根據【你的參考資料】；資料不足時標 [推論] 並說明不確定。"
        f"繁體中文，{length_hint}。"
    )
    user = (
        f"【你的參考資料】\n{context}\n\n"
        f"【先前討論】\n{history_text or '（無）'}\n"
        f"{others}\n\n"
        f"【議題】\n{discussion_brief}\n\n"
        f"【主題契合度】{score}/100\n\n"
        f"請以{name_zh}身份發言：先呼應他人一句，再提出你的論點（句尾 [編號] 或 [推論]）。"
    )
    return _llm(client, model, system, user, temperature=temp)


def _generate_conclusion(
    client: Any,
    model: str,
    *,
    topic: str,
    discussion_brief: str,
    transcript: str,
    participant_names: list[str],
) -> str:
    guests = "、".join(participant_names)
    system = (
        "你是圓桌主持人，根據討論紀錄產出結論。"
        "繁體中文：重述議題、共識、分歧、建議。約 180～260 字。不需標註引用。"
    )
    user = (
        f"【主題】{topic}\n【議題】{discussion_brief}\n【與會】{guests}\n\n"
        f"【紀錄】\n{transcript}\n\n請產出討論結論。"
    )
    return _llm(client, model, system, user, temperature=0.5)


def _prior_since_last_user(
    messages: list[dict[str, Any]],
    user_name: str,
) -> list[dict[str, str]]:
    """使用者上一則插話之後的發言（用於插話後的單輪討論）。"""
    acc: list[dict[str, str]] = []
    for m in reversed(messages):
        if m.get("role") == "user":
            break
        if m.get("role") == "user_twin":
            acc.insert(0, {"name": f"{user_name}（分身）", "content": m["content"]})
        elif m.get("person_name_zh"):
            acc.insert(0, {"name": m["person_name_zh"], "content": m["content"]})
    return acc


def _prior_in_same_phase(
    messages: list[dict[str, Any]],
    phase: str,
    user_name: str,
) -> list[dict[str, str]]:
    """本 phase 內、本則結論前已發言者（用於開場/辯論輪序提示）。"""
    acc: list[dict[str, str]] = []
    for m in reversed(messages):
        if m.get("role") == "conclusion":
            break
        meta_phase = m.get("phase")
        if meta_phase and meta_phase != phase:
            continue
        if m.get("role") == "user":
            break
        if m.get("role") == "user_twin":
            acc.insert(0, {"name": f"{user_name}（分身）", "content": m["content"]})
        elif m.get("person_name_zh"):
            acc.insert(0, {"name": m["person_name_zh"], "content": m["content"]})
    return acc


def run_next_turn(
    *,
    session_id: int,
    members: list[dict[str, Any]],
    topic: str,
    user_name: str,
    twin_context: str,
    client: Any,
    model: str,
    top_k: int = 8,
    discussion_brief: str | None = None,
    include_user_twin: bool = True,
    user_avatar_url: str = "",
    user_id: int | None = None,
) -> dict[str, Any] | None:
    """執行下一則發言；若已全部完成則回傳 None。"""
    history = chat_store.list_messages(session_id)
    spec = get_next_turn(history, members, include_user_twin=include_user_twin)
    if not spec:
        return None

    brief = _discussion_brief(topic, discussion_brief or "")
    user_note = _latest_user_note(history, members, user_name)
    if user_note:
        brief = f"{brief}\n\n【使用者剛剛插話】{user_note}"

    history_text = _format_transcript(history, user_name, exclude_roles={"conclusion"})
    twin_label = f"{user_name}（分身）"
    celeb_names = [m["name_zh"] for m in members]

    if spec.kind == "user_twin":
        raw, chunk_ids, sources = _reply_user_twin(
            client,
            model,
            user_name=user_name,
            topic=topic,
            twin_context=twin_context,
            discussion_brief=brief,
            history_text=history_text,
            phase=spec.phase,
            user_id=user_id,
            session_id=session_id,
            top_k=top_k,
        )
        display, segments = parse_cited_reply(raw, sources)
        msg = chat_store.add_message(
            session_id,
            "user_twin",
            display,
            chunk_ids=chunk_ids,
            sources=sources,
            content_segments=segments,
            phase=spec.phase,
        )
        out = {
            **msg,
            "person_slug": None,
            "person_name_zh": twin_label,
            "avatar_url": user_avatar_url,
            "phase": spec.phase,
            "sources": sources,
            "content_segments": segments,
        }
        return out

    if spec.kind == "conclusion":
        participants = celeb_names + ([twin_label] if include_user_twin else [])
        text = _generate_conclusion(
            client,
            model,
            topic=topic,
            discussion_brief=brief,
            transcript=history_text,
            participant_names=participants,
        )
        msg = chat_store.add_message(
            session_id,
            "conclusion",
            text,
            chunk_ids=[],
            sources=[],
            phase="conclusion",
        )
        chat_store.update_session_summary(session_id, text[:2000])
        return {
            **msg,
            "person_slug": None,
            "person_name_zh": "討論結論",
            "phase": "conclusion",
            "sources": [],
            "content_segments": [],
        }

    member = spec.member
    if not member:
        return None

    slug = member["person_slug"]
    name_zh = member["name_zh"]
    rag_q = f"{topic} {brief}"
    if spec.phase == "debate":
        rag_q += " " + history_text[-500:]

    fit_top_k = _rag_top_k_for_fit(member.get("topic_fit_score"), top_k)
    context, chunk_ids, sources = _rag_context(slug, rag_q, fit_top_k)
    context, chunk_ids, sources = _append_session_context(
        context,
        chunk_ids,
        sources,
        user_id=user_id,
        session_id=session_id,
        query=rag_q,
        top_k=fit_top_k,
    )
    prior = _prior_in_same_phase(history, spec.phase, user_name)

    raw = _reply_celeb(
        client,
        model,
        name_zh=name_zh,
        topic=topic,
        discussion_brief=brief,
        history_text=history_text,
        context=context,
        phase=spec.phase,
        prior_in_round=prior,
        topic_fit_score=member.get("topic_fit_score"),
    )
    display, segments = parse_cited_reply(raw, sources)
    packed = _pack_sources(sources, segments)
    if isinstance(packed, dict):
        packed["phase"] = spec.phase

    msg = chat_store.add_message(
        session_id,
        slug,
        display,
        person_slug=slug,
        chunk_ids=chunk_ids,
        sources=packed,
        phase=spec.phase,
        content_segments=segments,
    )
    return {
        **msg,
        "person_slug": slug,
        "person_name_zh": name_zh,
        "avatar_url": member.get("avatar_url") or "",
        "phase": spec.phase,
        "sources": sources,
        "content_segments": segments,
        "content_raw": raw,
    }


def _interjection_brief(
    topic: str,
    discussion_brief: str | None,
    history: list[dict[str, Any]],
    members: list[dict[str, Any]],
    user_name: str,
) -> str:
    brief = _discussion_brief(topic, discussion_brief or "")
    user_note = _latest_user_note(history, members, user_name)
    if user_note:
        brief = f"{brief}\n\n【使用者剛剛插話】{user_note}"
    return brief


def run_direct_reply(
    *,
    session_id: int,
    members: list[dict[str, Any]],
    topic: str,
    user_name: str,
    twin_context: str,
    client: Any,
    model: str,
    target: str,
    top_k: int = 8,
    discussion_brief: str | None = None,
    include_user_twin: bool = True,
    user_avatar_url: str = "",
    user_id: int | None = None,
) -> dict[str, Any] | None:
    """插話後只讓單一對象回應一次（名人 slug 或 user_twin）。"""
    target = (target or "").strip()
    if target == "all":
        return None
    if target == "user_twin" and not include_user_twin:
        return None

    history = chat_store.list_messages(session_id)
    brief = _interjection_brief(topic, discussion_brief, history, members, user_name)
    history_text = _format_transcript(history, user_name, exclude_roles={"conclusion"})
    phase = "debate"
    prior = _prior_since_last_user(history, user_name)
    twin_label = f"{user_name}（分身）"
    last_reply_to = ""
    for m in reversed(history):
        if m.get("role") == "user":
            last_reply_to = (m.get("reply_to") or "all").strip() or "all"
            break

    if target == "user_twin":
        raw, chunk_ids, sources = _reply_user_twin(
            client,
            model,
            user_name=user_name,
            topic=topic,
            twin_context=twin_context,
            discussion_brief=brief,
            history_text=history_text,
            phase=phase,
            user_id=user_id,
            session_id=session_id,
            top_k=top_k,
        )
        display, segments = parse_cited_reply(raw, sources)
        msg = chat_store.add_message(
            session_id,
            "user_twin",
            display,
            chunk_ids=chunk_ids,
            sources=sources,
            content_segments=segments,
            phase=phase,
        )
        return {
            **msg,
            "person_slug": None,
            "person_name_zh": twin_label,
            "avatar_url": user_avatar_url,
            "phase": phase,
            "sources": sources,
            "content_segments": segments,
        }

    member = next(
        (m for m in members if (m.get("person_slug") or "") == target),
        None,
    )
    if not member:
        return None

    slug = member["person_slug"]
    name_zh = member["name_zh"]
    direct = last_reply_to == slug
    rag_q = f"{topic} {brief} {history_text[-500:]}"
    fit_top_k = _rag_top_k_for_fit(member.get("topic_fit_score"), top_k)
    context, chunk_ids, sources = _rag_context(slug, rag_q, fit_top_k)
    context, chunk_ids, sources = _append_session_context(
        context,
        chunk_ids,
        sources,
        user_id=user_id,
        session_id=session_id,
        query=rag_q,
        top_k=fit_top_k,
    )
    raw = _reply_celeb(
        client,
        model,
        name_zh=name_zh,
        topic=topic,
        discussion_brief=brief,
        history_text=history_text,
        context=context,
        phase=phase,
        prior_in_round=prior,
        topic_fit_score=member.get("topic_fit_score"),
        direct_address=direct,
    )
    display, segments = parse_cited_reply(raw, sources)
    packed = _pack_sources(sources, segments)
    if isinstance(packed, dict):
        packed["phase"] = phase
        if direct:
            packed["direct_reply"] = True
            packed["reply_to"] = slug
    msg = chat_store.add_message(
        session_id,
        slug,
        display,
        person_slug=slug,
        chunk_ids=chunk_ids,
        sources=packed,
        phase=phase,
        content_segments=segments,
    )
    return {
        **msg,
        "person_slug": slug,
        "person_name_zh": name_zh,
        "avatar_url": member.get("avatar_url") or "",
        "phase": phase,
        "sources": sources,
        "content_segments": segments,
    }


def run_interjection_round(
    *,
    session_id: int,
    members: list[dict[str, Any]],
    topic: str,
    user_name: str,
    twin_context: str,
    client: Any,
    model: str,
    top_k: int = 8,
    discussion_brief: str | None = None,
    include_user_twin: bool = True,
    user_avatar_url: str = "",
    user_id: int | None = None,
) -> dict[str, Any]:
    """插話給所有人：隨機名人順序，一位接一位回應（非同時）。"""
    ordered = [m for m in members if (m.get("person_slug") or m.get("slug") or "").strip()]
    random.shuffle(ordered)
    speaking_order: list[dict[str, Any]] = []
    replies: list[dict[str, Any]] = []

    for m in ordered:
        slug = m.get("person_slug") or ""
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
        msg = run_direct_reply(
            session_id=session_id,
            members=members,
            topic=topic,
            user_name=user_name,
            twin_context=twin_context,
            client=client,
            model=model,
            target=slug,
            top_k=top_k,
            discussion_brief=discussion_brief,
            include_user_twin=include_user_twin,
            user_avatar_url=user_avatar_url,
            user_id=user_id,
        )
        if msg:
            msg["interjection_index"] = len(replies) + 1
            replies.append(msg)

    if include_user_twin:
        twin_label = f"{user_name}（分身）"
        speaking_order.append(
            {
                "person_slug": "user_twin",
                "name_zh": twin_label,
                "avatar_url": user_avatar_url,
                "kind": "user_twin",
                "topic_fit_score": None,
            }
        )
        twin_msg = run_direct_reply(
            session_id=session_id,
            members=members,
            topic=topic,
            user_name=user_name,
            twin_context=twin_context,
            client=client,
            model=model,
            target="user_twin",
            top_k=top_k,
            discussion_brief=discussion_brief,
            include_user_twin=include_user_twin,
            user_avatar_url=user_avatar_url,
            user_id=user_id,
        )
        if twin_msg:
            twin_msg["interjection_index"] = len(replies) + 1
            replies.append(twin_msg)

    total = len(replies)
    for msg in replies:
        msg["interjection_total"] = total

    return {"speaking_order": speaking_order, "replies": replies}


def run_roundtable(**kwargs: Any) -> list[dict[str, Any]]:
    """相容舊 API：改為迴圈呼叫 run_next_turn。"""
    out: list[dict[str, Any]] = []
    session_id = kwargs["session_id"]
    members = kwargs["members"]
    while True:
        msg = run_next_turn(**kwargs)
        if not msg:
            break
        out.append(msg)
    return out
