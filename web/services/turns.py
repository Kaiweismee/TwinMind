"""討論推進流程：產生下一則發言與讀取下一位發言者。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from web.core.dependencies import _resolve_top_k
from web.repositories import chat_store
from web.conversations import discussion
from web.services.ai import _discussion_client


def _run_single_turn(
    session_id: int,
    *,
    top_k: int | None = None,
    discussion_brief: str | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    session = chat_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="找不到聊天室")

    members = session.get("members") or []
    if not members:
        raise HTTPException(status_code=400, detail="此聊天室沒有參與的名人")

    client, model = _discussion_client()
    profile = profile or chat_store.get_profile()
    user_name = profile.get("display_name") or "你"
    topic = session.get("topic") or "討論"
    messages = chat_store.list_messages(session_id)

    merged_brief = discussion_brief
    ctx = (session.get("context_brief") or "").strip()
    if ctx:
        merged_brief = f"{ctx}\n\n{merged_brief}" if merged_brief else ctx

    msg = discussion.run_next_turn(
        session_id=session_id,
        members=members,
        topic=topic,
        user_name=user_name,
        twin_context=profile.get("twin_context") or "",
        client=client,
        model=model,
        top_k=_resolve_top_k(top_k),
        discussion_brief=merged_brief,
        user_avatar_url=profile.get("avatar_url") or "",
        user_id=profile.get("id"),
    )
    done = msg is None
    fresh = chat_store.list_messages(session_id)
    next_label = None if done else discussion.peek_next_turn_label(
        fresh, members, user_name
    )
    next_speaker = None if done else discussion.peek_next_speaker(
        fresh,
        members,
        user_name,
        user_avatar_url=profile.get("avatar_url") or "",
    )
    return {
        "done": done,
        "message": msg,
        "next_label": next_label,
        "next_speaker": next_speaker,
    }


def _turn_state(
    session_id: int,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    session = chat_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="找不到聊天室")
    members = session.get("members") or []
    profile = profile or chat_store.get_profile()
    user_name = profile.get("display_name") or "你"
    messages = chat_store.list_messages(session_id)
    next_label = discussion.peek_next_turn_label(messages, members, user_name)
    next_speaker = discussion.peek_next_speaker(
        messages,
        members,
        user_name,
        user_avatar_url=profile.get("avatar_url") or "",
    )
    return {
        "done": next_label is None,
        "next_label": next_label,
        "next_speaker": next_speaker,
        "message_count": len(messages),
    }
