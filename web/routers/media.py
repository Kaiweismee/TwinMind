"""媒體庫 API：彙整個人分身、名人私聊與討論室附件。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query

from web.core.dependencies import require_user
from web.repositories import chat_store
from web.conversations import person_chat
from web.conversations import twin_chat


router = APIRouter()


@router.get("/api/media-library")
def api_media_library(
    limit: int = Query(500, ge=1, le=1200),
    user: dict[str, Any] = Depends(require_user),
):
    twin_items = twin_chat.list_user_media_files(user["id"], limit=min(limit, 600))
    person_items = person_chat.list_user_media_files(user["id"], limit=min(limit, 300))
    session_items = chat_store.list_user_session_media_files(
        user["id"], limit=min(limit, 300)
    )
    merged = twin_items + person_items + session_items
    merged.sort(
        key=lambda x: x.get("created_at") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    merged = merged[:limit]
    return {
        "items": merged,
        "count": len(merged),
        "image_count": sum(1 for i in merged if (i.get("file") or {}).get("kind") == "image"),
        "file_count": sum(1 for i in merged if (i.get("file") or {}).get("kind") != "image"),
    }
