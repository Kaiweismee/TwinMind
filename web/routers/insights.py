"""討論分析 API：心智圖、立場曲線與分析快取。"""

from __future__ import annotations

from typing import Any
import os

from fastapi import APIRouter, Depends, HTTPException, Header, Query

from web.core.dependencies import _enforce_session_access, require_user
from web.repositories import chat_store
from web.conversations import discussion_insights
from web.core.runtime import _log
from web.services.ai import _discussion_client


router = APIRouter()


@router.get("/api/sessions/{session_id}/insights")
def api_session_insights(
    session_id: int,
    refresh: bool = Query(False),
    live: bool = Query(False, description="每則發言後即時重畫心智圖（規則版，不跑 LLM）"),
    max_messages: int | None = Query(
        None,
        ge=0,
        le=500,
        description="僅納入前 N 則訊息（思考中預覽，不含尚未顯示的回覆）",
    ),
    x_session_owner: str | None = Header(None, alias="X-Session-Owner"),
    user: dict[str, Any] = Depends(require_user),
):
    """依討論內容產生心智圖與意見差距曲線資料。"""
    _enforce_session_access(
        session_id,
        x_session_owner=x_session_owner,
        user=user,
    )
    session = chat_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="找不到聊天室")
    messages = chat_store.list_messages(session_id)
    if max_messages is not None:
        messages = messages[:max_messages]
    msg_count = len(chat_store.list_messages(session_id))
    if not refresh and not live:
        cached = discussion_insights.get_cached_insights(session_id, msg_count)
        if cached:
            return {
                "insights": cached,
                "message_count": msg_count,
                "cached": True,
                "persisted": True,
            }
        snap = discussion_insights.get_stored_insights_snapshot(session_id)
        if snap and snap["message_count"] < msg_count:
            stale = dict(snap["insights"])
            stale["stale"] = True
            stale["stored_message_count"] = snap["message_count"]
            return {
                "insights": stale,
                "message_count": msg_count,
                "cached": True,
                "persisted": True,
                "stale": True,
            }

    topic = session.get("topic") or session.get("title") or "討論"
    members = session.get("members") or []
    client = None
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    try:
        client, model = _discussion_client()
    except HTTPException:
        client = None

    try:
        insights = discussion_insights.build_session_insights(
            session_id=session_id,
            topic=topic,
            members=members,
            messages=messages,
            message_count=msg_count,
            client=client,
            model=model,
            force=refresh,
            live_only=live and not refresh,
        )
    except Exception as exc:
        _log.exception("session insights failed: %s", exc)
        insights = discussion_insights.build_session_insights(
            session_id=session_id,
            topic=topic,
            members=members,
            messages=messages,
            message_count=msg_count,
            client=None,
            force=False,
            live_only=True,
        )
        insights["update_label"] = "即時更新（分析暫時失敗，已改用規則版）"

    insights["message_count"] = msg_count
    discussion_insights.set_cached_insights(session_id, msg_count, insights)
    return {
        "insights": insights,
        "message_count": msg_count,
        "cached": False,
        "persisted": True,
        "live": live and not refresh,
        "update_mode": insights.get("update_mode") or "live",
    }
