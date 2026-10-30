"""一對一數位分身對話（含檔案上傳）"""

from __future__ import annotations

import base64
import mimetypes
import os
import secrets
import uuid
from pathlib import Path
from typing import Any

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from web.core.rag_backend import DB_CONFIG

from web.core.settings import ROOT
UPLOAD_ROOT = ROOT / "data" / "twin_uploads"
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_HISTORY = 40
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".log"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _conn():
    return psycopg2.connect(**DB_CONFIG)


def ensure_twin_chat_schema() -> None:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_twin_chat_messages (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL
                        REFERENCES users(id) ON DELETE CASCADE,
                    twin_id INTEGER NOT NULL
                        REFERENCES user_twins(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL DEFAULT '',
                    attachments JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_twin_chat_user_twin
                ON user_twin_chat_messages(user_id, twin_id, created_at);
                """
            )
        conn.commit()
    finally:
        conn.close()


def _safe_filename(name: str) -> str:
    base = os.path.basename(name or "file")
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in base)[:120]


def _user_upload_dir(user_id: int) -> Path:
    d = UPLOAD_ROOT / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_upload(user_id: int, filename: str, data: bytes) -> dict[str, Any]:
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"檔案過大（上限 {MAX_FILE_BYTES // (1024 * 1024)} MB）")
    safe = _safe_filename(filename)
    ext = Path(safe).suffix.lower()
    stored = f"{uuid.uuid4().hex}_{safe}"
    path = _user_upload_dir(user_id) / stored
    path.write_bytes(data)

    mime = mimetypes.guess_type(safe)[0] or "application/octet-stream"
    kind = "image" if ext in IMAGE_EXTENSIONS or mime.startswith("image/") else "file"
    preview = ""
    if ext in TEXT_EXTENSIONS or ext in DOCUMENT_EXTENSIONS:
        from web.knowledge.file_extract import preview_text

        preview = preview_text(safe, data)

    item: dict[str, Any] = {
        "id": secrets.token_hex(8),
        "name": safe,
        "stored_name": stored,
        "mime": mime,
        "kind": kind,
        "size": len(data),
        "url": f"/api/twin-chat/files/{user_id}/{stored}",
    }
    if preview:
        item["text_preview"] = preview
    if kind == "image":
        item["data_url"] = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
    return item


def get_upload_path(user_id: int, stored_name: str) -> Path | None:
    safe = _safe_filename(stored_name)
    path = _user_upload_dir(user_id) / safe
    if not path.is_file():
        return None
    return path


def list_messages(user_id: int, twin_id: int, *, limit: int = 80) -> list[dict[str, Any]]:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, role, content, attachments, created_at
                FROM user_twin_chat_messages
                WHERE user_id = %s AND twin_id = %s
                ORDER BY created_at ASC
                LIMIT %s;
                """,
                (user_id, twin_id, limit),
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def list_user_media_files(user_id: int, *, limit: int = 300) -> list[dict[str, Any]]:
    """Collect uploaded files from user's twin chat history."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, twin_id, attachments, created_at
                FROM user_twin_chat_messages
                WHERE user_id = %s
                  AND jsonb_array_length(attachments) > 0
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (user_id, limit),
            )
            rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    items: list[dict[str, Any]] = []
    for row in rows:
        for raw in row.get("attachments") or []:
            a = dict(raw)
            a.pop("data_url", None)
            items.append(
                {
                    "source": "twin_chat",
                    "message_id": row.get("id"),
                    "twin_id": row.get("twin_id"),
                    "created_at": row.get("created_at"),
                    "file": a,
                }
            )
    return items


def insert_message(
    user_id: int,
    twin_id: int,
    *,
    role: str,
    content: str,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO user_twin_chat_messages (
                    user_id, twin_id, role, content, attachments
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, role, content, attachments, created_at;
                """,
                (user_id, twin_id, role, content, Json(attachments or [])),
            )
            row = dict(cur.fetchone())
        conn.commit()
        return row
    finally:
        conn.close()


def _attachment_context(attachments: list[dict[str, Any]]) -> str:
    if not attachments:
        return ""
    parts: list[str] = []
    for a in attachments:
        name = a.get("name") or "檔案"
        if a.get("text_preview"):
            parts.append(f"【檔案：{name}】\n{a['text_preview'][:2000]}")
        elif a.get("kind") == "image":
            parts.append(f"【圖片：{name}】使用者分享了一張圖片。")
        else:
            parts.append(f"【檔案：{name}】使用者上傳了檔案。")
    return "\n\n".join(parts)


def generate_reply(
    *,
    profile: dict[str, Any],
    twin_name: str,
    history: list[dict[str, Any]],
    user_text: str,
    attachments: list[dict[str, Any]],
    client,
    model: str,
) -> str:
    system = (
        f"{profile.get('twin_context') or ''}\n\n"
        "你正在與使用者一對一私聊，目的是更認識對方、記住對方分享的資訊。"
        "若使用者上傳圖片或檔案，請根據內容回應並簡短整理你學到的事。"
        "繁體中文，語氣自然，約 80～180 字。"
    )
    user_id = profile.get("id")
    if user_id:
        try:
            from web.knowledge import user_rag

            rag_q = (user_text or "").strip() or _attachment_context(attachments)
            if rag_q:
                rag_ctx, _, _ = user_rag.search_user_context(int(user_id), rag_q, top_k=6)
                system += f"\n\n【使用者私人資料庫（RAG）】\n{rag_ctx}"
        except Exception:
            pass
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]

    for msg in history[-MAX_HISTORY:]:
        role = "assistant" if msg["role"] == "assistant" else "user"
        text = (msg.get("content") or "").strip()
        att_ctx = _attachment_context(msg.get("attachments") or [])
        if att_ctx:
            text = f"{text}\n\n{att_ctx}".strip() if text else att_ctx
        if text:
            messages.append({"role": role, "content": text})

    user_parts: list[Any] = []
    user_text = (user_text or "").strip()
    if user_text:
        user_parts.append({"type": "text", "text": user_text})
    att_ctx = _attachment_context(attachments)
    if att_ctx and not user_text:
        user_parts.append({"type": "text", "text": att_ctx})
    elif att_ctx:
        user_parts.append({"type": "text", "text": att_ctx})

    for a in attachments:
        if a.get("kind") == "image" and a.get("data_url"):
            user_parts.append({"type": "image_url", "image_url": {"url": a["data_url"]}})

    if not user_parts:
        user_parts.append({"type": "text", "text": "（使用者分享了檔案）"})

    messages.append({"role": "user", "content": user_parts})

    resp = client.chat.completions.create(model=model, messages=messages)
    return (resp.choices[0].message.content or "").strip() or "我在，繼續說吧。"
