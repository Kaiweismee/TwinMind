"""個人分身私聊 API：讀取訊息、傳送訊息與取得附件。"""

from __future__ import annotations

from typing import Any
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from web.core.dependencies import require_user
from web.conversations import twin_chat
from web.knowledge import user_rag
from web.services.ai import _require_openai


router = APIRouter()


@router.get("/api/twin-chat/messages")
def api_twin_chat_messages(user: dict[str, Any] = Depends(require_user)):
    twin_id = user.get("active_twin_id")
    if not twin_id:
        raise HTTPException(status_code=400, detail="請先選擇數位分身")
    messages = twin_chat.list_messages(user["id"], twin_id)
    return {"messages": messages, "twin_id": twin_id}


@router.get("/api/twin-chat/files/{user_id}/{stored_name}")
def api_twin_chat_file(
    user_id: int,
    stored_name: str,
    user: dict[str, Any] = Depends(require_user),
):
    if user["id"] != user_id:
        raise HTTPException(status_code=403, detail="無權限")
    path = twin_chat.get_upload_path(user_id, stored_name)
    if not path:
        raise HTTPException(status_code=404, detail="找不到檔案")
    return FileResponse(path)


@router.post("/api/twin-chat/messages")
async def api_twin_chat_send(
    content: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    user: dict[str, Any] = Depends(require_user),
):
    twin_id = user.get("active_twin_id")
    if not twin_id:
        raise HTTPException(status_code=400, detail="請先選擇數位分身")

    text = (content or "").strip()
    attachments: list[dict[str, Any]] = []
    for f in files or []:
        if not f.filename:
            continue
        data = await f.read()
        if not data:
            continue
        try:
            attachments.append(twin_chat.save_upload(user["id"], f.filename, data))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    if not text and not attachments:
        raise HTTPException(status_code=400, detail="請輸入訊息或上傳檔案")

    user_row = twin_chat.insert_message(
        user["id"],
        twin_id,
        role="user",
        content=text,
        attachments=attachments,
    )

    try:
        user_rag.ingest_twin_chat_message(
            user["id"],
            twin_id,
            message_id=int(user_row["id"]),
            role="user",
            content=text,
            attachments=attachments,
            twin_name=user.get("twin_name") or "分身",
            display_name=user.get("display_name") or user.get("username") or "使用者",
        )
    except Exception:
        pass

    try:
        api_key = _require_openai()
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        history = twin_chat.list_messages(user["id"], twin_id)
        reply = twin_chat.generate_reply(
            profile=user,
            twin_name=user.get("twin_name") or "分身",
            history=history[:-1],
            user_text=text,
            attachments=attachments,
            client=client,
            model=model,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    assistant_row = twin_chat.insert_message(
        user["id"],
        twin_id,
        role="assistant",
        content=reply,
        attachments=[],
    )
    return {"user_message": user_row, "assistant_message": assistant_row}
