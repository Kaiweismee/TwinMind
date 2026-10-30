"""討論室 API：建立、加入、讀取、置頂、刪除與上傳參考資料。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Header, Query, UploadFile

from web.core.dependencies import _enforce_session_access, require_user
from web.repositories import chat_store
from web.repositories import user_store
from web.schemas.requests import CreateSessionRequest, JoinSessionRequest, PinSessionRequest


router = APIRouter()


@router.get("/api/sessions")
def api_sessions(
    ids: str = Query("", description="逗號分隔的聊天室 id（本機已建立/已加入）"),
    include_public: bool = Query(False, description="保留欄位（目前未使用）"),
    user: dict[str, Any] = Depends(require_user),
):
    session_ids: list[int] = []
    if ids.strip():
        for part in ids.split(","):
            part = part.strip()
            if part.isdigit():
                session_ids.append(int(part))
    sessions = chat_store.list_sessions(
        session_ids=session_ids or None,
        public_only=False,
        owner_user_id=(user["id"] if not session_ids else None),
    )
    return {"sessions": sessions}


@router.get("/api/sessions/all-ids")
def api_all_session_ids():
    """一次性遷移：把既有聊天室 id 存進本機"""
    return {"ids": chat_store.list_all_session_ids()}


@router.post("/api/sessions")
def api_create_session(
    body: CreateSessionRequest,
    user: dict[str, Any] = Depends(require_user),
):
    slugs = [s.strip() for s in body.person_slugs if s.strip()]
    if not slugs and body.person_slug.strip():
        slugs = [body.person_slug.strip()]
    if not slugs:
        raise HTTPException(status_code=400, detail="請至少選擇一位名人")
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="請輸入討論主題")
    try:
        pwd = body.room_password.strip() if body.allow_guest_join else ""
        session = chat_store.create_session(
            slugs,
            body.title.strip(),
            room_password=pwd or None,
            owner_user_id=user["id"],
            allow_guest_join=body.allow_guest_join,
        )
        return {"session": session}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/api/sessions/{session_id}/context")
async def api_upload_session_context(
    session_id: int,
    files: list[UploadFile] = File(default=[]),
    user: dict[str, Any] = Depends(require_user),
):
    """建立討論室後上傳參考檔案，供名人與分身依資料討論。"""
    owner_id = user_store.get_session_owner_user_id(session_id)
    if owner_id is None or owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="僅房主可上傳參考資料")

    session = chat_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="找不到聊天室")

    from web.knowledge import session_context

    payload: list[tuple[str, bytes]] = []
    for f in files or []:
        if not f.filename:
            continue
        data = await f.read()
        if data:
            payload.append((f.filename, data))
    if not payload:
        raise HTTPException(status_code=400, detail="請選擇至少一個檔案")

    try:
        result = session_context.ingest_session_files(
            user["id"],
            session_id,
            session.get("topic") or "",
            payload,
            display_name=user.get("display_name") or user.get("account_name") or "使用者",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    chat_store.update_session_context(
        session_id,
        context_brief=result.get("context_brief") or "",
        context_files=result.get("context_files") or [],
    )
    return {
        "session_id": session_id,
        "context_brief": result.get("context_brief") or "",
        "context_files": result.get("context_files") or [],
        "ingested": result.get("ingested", 0),
    }


@router.patch("/api/sessions/{session_id}/pin")
def api_pin_session(
    session_id: int,
    body: PinSessionRequest,
    x_session_owner: str | None = Header(None, alias="X-Session-Owner"),
    user: dict[str, Any] = Depends(require_user),
):
    _enforce_session_access(
        session_id,
        x_session_owner=x_session_owner,
        user=user,
    )
    row = chat_store.set_session_pinned(session_id, body.pinned)
    if not row:
        raise HTTPException(status_code=404, detail="找不到聊天室")
    return {"session_id": session_id, "pinned": row["pinned"]}


@router.delete("/api/sessions/{session_id}")
def api_delete_session(
    session_id: int,
    user: dict[str, Any] = Depends(require_user),
):
    deleted = chat_store.delete_session_for_user(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="找不到聊天室")
    return {"ok": True, "session_id": session_id}


@router.get("/api/sessions/preview/{join_code}")
def api_session_preview(join_code: str, user: dict[str, Any] = Depends(require_user)):
    preview = chat_store.get_session_by_join_code(join_code)
    if not preview:
        raise HTTPException(status_code=404, detail="找不到此加入碼")
    return {
        "id": preview["id"],
        "topic": preview["topic"],
        "join_code": preview["join_code"],
        "has_password": preview.get("has_password", False),
        "members_label": preview.get("members_label", ""),
    }


@router.post("/api/sessions/join")
def api_join_session(body: JoinSessionRequest, user: dict[str, Any] = Depends(require_user)):
    try:
        return chat_store.join_session_for_user(
            body.join_code.strip(),
            int(user["id"]),
            display_name=body.guest_name.strip() or None,
            password=body.password.strip() or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/api/sessions/{session_id}")
def api_get_session(
    session_id: int,
    x_session_owner: str | None = Header(None, alias="X-Session-Owner"),
    user: dict[str, Any] = Depends(require_user),
):
    _enforce_session_access(
        session_id,
        x_session_owner=x_session_owner,
        user=user,
    )
    session = chat_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="找不到聊天室")
    messages = chat_store.list_messages(session_id)
    return {"session": session, "messages": messages}
