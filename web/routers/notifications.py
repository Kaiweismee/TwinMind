"""通知 API：加入通知與已讀狀態。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from web.core.dependencies import require_user
from web.repositories import chat_store
from web.schemas.requests import MarkNotificationsReadRequest


router = APIRouter()


@router.get("/api/notifications")
def api_notifications(
    ids: str = Query("", description="房主擁有的 session id，逗號分隔"),
    unread_only: bool = Query(True),
    user: dict[str, Any] = Depends(require_user),
):
    session_ids = [
        int(p.strip()) for p in ids.split(",") if p.strip().isdigit()
    ]
    owner_user_id = user.get("id") if not session_ids else None
    items = chat_store.list_join_notifications(
        session_ids,
        unread_only=unread_only,
        owner_user_id=owner_user_id,
    )
    unread_count = chat_store.count_unread_notifications(
        session_ids,
        owner_user_id=owner_user_id,
    )
    return {"notifications": items, "unread_count": unread_count}


@router.post("/api/notifications/read")
def api_mark_notifications_read(
    body: MarkNotificationsReadRequest,
    user: dict[str, Any] = Depends(require_user),
):
    owner_user_id = (
        user.get("id") if not body.session_ids and not body.notification_ids else None
    )
    n = chat_store.mark_notifications_read(
        session_ids=body.session_ids or None,
        notification_ids=body.notification_ids or None,
        owner_user_id=owner_user_id,
    )
    return {"marked": n}
