"""分身管理 API：清單、建立、切換與上傳背景資料。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from web.core.dependencies import _profile_for_user, require_user
from web.conversations import twin_chat
from web.knowledge import user_rag
from web.repositories import user_store
from web.schemas.requests import CreateTwinRequest


router = APIRouter()


@router.get("/api/twins")
def api_list_twins(user: dict[str, Any] = Depends(require_user)):
    twins = user_store.list_user_twins(user["id"])
    return {"twins": twins, "active_twin_id": user.get("active_twin_id")}


@router.post("/api/twins")
def api_create_twin(body: CreateTwinRequest, user: dict[str, Any] = Depends(require_user)):
    try:
        twin = user_store.create_twin(
            user["id"],
            name=body.name,
            preset=body.preset,
            bio=body.bio,
            twin_context=body.twin_context or None,
        )
        profile = user_store.get_user_profile_by_id(user["id"])
        return {"twin": twin, "user": _profile_for_user(profile)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/api/twins/{twin_id}/activate")
def api_activate_twin(twin_id: int, user: dict[str, Any] = Depends(require_user)):
    try:
        profile = user_store.activate_twin(user["id"], twin_id)
        return {"user": _profile_for_user(profile)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/api/twins/{twin_id}/context-files")
async def api_upload_twin_context_files(
    twin_id: int,
    files: list[UploadFile] = File(default=[]),
    user: dict[str, Any] = Depends(require_user),
):
    twins = user_store.list_user_twins(user["id"])
    if not any(int(t.get("id", -1)) == twin_id for t in twins):
        raise HTTPException(status_code=403, detail="無權限上傳到此分身")
    payload: list[dict[str, Any]] = []
    for f in files or []:
        if not f.filename:
            continue
        data = await f.read()
        if not data:
            continue
        try:
            payload.append(twin_chat.save_upload(user["id"], f.filename, data))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    if not payload:
        raise HTTPException(status_code=400, detail="請至少選擇一個檔案")

    msg = twin_chat.insert_message(
        user["id"],
        twin_id,
        role="user",
        content="（建立分身時上傳的個人文字資料）",
        attachments=payload,
    )
    try:
        user_rag.ingest_twin_chat_message(
            user["id"],
            twin_id,
            message_id=int(msg["id"]),
            role="user",
            content=msg.get("content") or "",
            attachments=payload,
            twin_name=next((t.get("name") for t in twins if int(t.get("id", -1)) == twin_id), "")
            or user.get("twin_name")
            or "分身",
            display_name=user.get("display_name") or user.get("username") or "使用者",
        )
    except Exception:
        pass
    return {"uploaded": len(payload), "files": payload}
