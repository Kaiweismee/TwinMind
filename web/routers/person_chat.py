"""名人私聊 API：對話清單、訊息與刪除對話。"""

from __future__ import annotations

from typing import Any
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from web.core.dependencies import require_user
from web.conversations import person_chat
from web.conversations import twin_chat
from web.services.ai import _require_openai


router = APIRouter()


@router.get("/api/person-chat/threads")
def api_person_chat_threads(
    limit: int = Query(80, ge=1, le=200),
    user: dict[str, Any] = Depends(require_user),
):
    threads = person_chat.list_threads(user["id"], limit=limit)
    return {"threads": threads}


@router.delete("/api/person-chat/threads/{person_slug}")
def api_person_chat_delete_thread(
    person_slug: str,
    user: dict[str, Any] = Depends(require_user),
):
    slug = (person_slug or "").strip()
    if not slug:
        raise HTTPException(status_code=400, detail="缺少名人代號")
    deleted = person_chat.delete_thread(user["id"], slug)
    if not deleted:
        raise HTTPException(status_code=404, detail="找不到對話紀錄")
    return {"ok": True, "deleted": deleted}


@router.get("/api/person-chat/messages")
def api_person_chat_messages(
    person_slug: str = Query(..., min_length=1),
    user: dict[str, Any] = Depends(require_user),
):
    slug = person_slug.strip()
    person = person_chat.get_person(slug)
    if not person:
        raise HTTPException(status_code=404, detail="找不到名人")
    messages = person_chat.list_messages(user["id"], slug)
    return {"messages": messages, "person": person}


@router.post("/api/person-chat/messages")
async def api_person_chat_send(
    person_slug: str = Form(...),
    content: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    user: dict[str, Any] = Depends(require_user),
):
    slug = (person_slug or "").strip()
    if not slug:
        raise HTTPException(status_code=400, detail="缺少名人代號")
    person = person_chat.get_person(slug)
    if not person:
        raise HTTPException(status_code=404, detail="找不到名人")

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

    user_row = person_chat.insert_message(
        user["id"],
        slug,
        role="user",
        content=text,
        attachments=attachments,
    )

    try:
        api_key = _require_openai()
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        history = person_chat.list_messages(user["id"], slug)
        reply = person_chat.generate_reply(
            person=person,
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

    assistant_row = person_chat.insert_message(
        user["id"],
        slug,
        role="assistant",
        content=reply,
    )
    return {"user_message": user_row, "assistant_message": assistant_row, "person": person}
