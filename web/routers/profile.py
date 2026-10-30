"""個人資料 API：名稱、自介與頭像。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4
import mimetypes
import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from web.core.dependencies import _profile_for_user, require_user
from web.repositories import user_store
from web.schemas.requests import ProfileAvatarPresetRequest, UpdateProfileRequest
from web.core.settings import MAX_PROFILE_AVATAR_BYTES, PROFILE_AVATAR_ROOT


router = APIRouter()


def _safe_upload_name(name: str) -> str:
    base = os.path.basename(name or "avatar")
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in base)[:120]


def _profile_avatar_path(user_id: int, stored_name: str) -> Path:
    return PROFILE_AVATAR_ROOT / str(user_id) / _safe_upload_name(stored_name)


@router.get("/api/profile")
def api_profile(user: dict[str, Any] = Depends(require_user)):
    return _profile_for_user(user)


@router.patch("/api/profile")
def api_update_profile(
    body: UpdateProfileRequest,
    user: dict[str, Any] = Depends(require_user),
):
    try:
        profile = user_store.update_user_profile(
            user["id"],
            display_name=body.display_name,
            bio=body.bio,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"user": _profile_for_user(profile)}


@router.post("/api/profile/avatar/preset")
def api_set_profile_avatar_preset(
    body: ProfileAvatarPresetRequest,
    user: dict[str, Any] = Depends(require_user),
):
    avatar_preset = (body.avatar_preset or "").strip()
    if not user_store.is_valid_register_avatar_preset(avatar_preset):
        raise HTTPException(status_code=400, detail="頭像選項無效")
    profile = user_store.update_user_profile(user["id"], avatar_url=avatar_preset)
    return {"avatar_url": avatar_preset, "user": _profile_for_user(profile)}


@router.post("/api/profile/avatar")
async def api_upload_profile_avatar(
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(require_user),
):
    filename = _safe_upload_name(file.filename or "avatar")
    ext = Path(filename).suffix.lower()
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="請選擇圖片檔案")
    if len(data) > MAX_PROFILE_AVATAR_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"頭像檔案過大（上限 {MAX_PROFILE_AVATAR_BYTES // (1024 * 1024)} MB）",
        )
    mime = (
        file.content_type
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream"
    )
    if not mime.startswith("image/"):
        raise HTTPException(status_code=400, detail="僅支援圖片檔案")
    if not ext:
        ext = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
            "image/gif": ".gif",
        }.get(mime, ".png")

    stored_name = f"{uuid4().hex}{ext}"
    dst = _profile_avatar_path(user["id"], stored_name)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)

    avatar_url = f"/api/profile/avatar/{user['id']}/{stored_name}"
    profile = user_store.update_user_profile(user["id"], avatar_url=avatar_url)
    return {"avatar_url": avatar_url, "user": _profile_for_user(profile)}


@router.get("/api/profile/avatar/{user_id}/{stored_name}")
def api_profile_avatar_file(user_id: int, stored_name: str):
    path = _profile_avatar_path(user_id, stored_name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="找不到頭像")
    return FileResponse(path)
