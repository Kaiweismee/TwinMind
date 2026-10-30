"""一對一名人數位分身對話"""

from __future__ import annotations

from typing import Any

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from web.core.rag_backend import DB_CONFIG
from web.core.rag_backend import format_context, search_chunks
from web.conversations import twin_chat

MAX_HISTORY = 40


def _conn():
    return psycopg2.connect(**DB_CONFIG)


def ensure_person_chat_schema() -> None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_person_chat_messages (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL
                        REFERENCES users(id) ON DELETE CASCADE,
                    person_slug TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL DEFAULT '',
                    attachments JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                ALTER TABLE user_person_chat_messages
                ADD COLUMN IF NOT EXISTS attachments JSONB NOT NULL DEFAULT '[]'::jsonb;
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_person_chat_user_slug
                ON user_person_chat_messages(user_id, person_slug, created_at);
                """
            )
        conn.commit()
    finally:
        conn.close()


def get_person(slug: str) -> dict[str, Any] | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT slug, name_zh, name_en, bio, avatar_url, category
                FROM persons
                WHERE slug = %s;
                """,
                (slug,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def list_messages(user_id: int, person_slug: str, *, limit: int = 80) -> list[dict[str, Any]]:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, role, content, attachments, created_at
                FROM user_person_chat_messages
                WHERE user_id = %s AND person_slug = %s
                ORDER BY created_at ASC
                LIMIT %s;
                """,
                (user_id, person_slug, limit),
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def list_threads(user_id: int, *, limit: int = 80) -> list[dict[str, Any]]:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT m.person_slug,
                       p.name_zh AS person_name_zh,
                       p.avatar_url,
                       (
                           SELECT lm.content
                           FROM user_person_chat_messages lm
                           WHERE lm.user_id = m.user_id
                             AND lm.person_slug = m.person_slug
                           ORDER BY lm.created_at DESC
                           LIMIT 1
                       ) AS last_message,
                       MIN(m.created_at) AS created_at,
                       MAX(m.created_at) AS updated_at,
                       COUNT(*)::int AS message_count
                FROM user_person_chat_messages m
                JOIN persons p ON p.slug = m.person_slug
                WHERE m.user_id = %s
                GROUP BY m.person_slug, p.name_zh, p.avatar_url, m.user_id
                ORDER BY MAX(m.created_at) DESC
                LIMIT %s;
                """,
                (user_id, limit),
            )
            rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    threads: list[dict[str, Any]] = []
    for row in rows:
        slug = row.get("person_slug") or ""
        name = row.get("person_name_zh") or slug
        threads.append(
            {
                "kind": "person_chat",
                "person_slug": slug,
                "topic": f"與 {name} 對話",
                "person_name_zh": name,
                "avatar_url": row.get("avatar_url") or "",
                "last_message": row.get("last_message") or "",
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
                "message_count": row.get("message_count") or 0,
                "members": [
                    {
                        "person_slug": slug,
                        "name_zh": name,
                        "avatar_url": row.get("avatar_url") or "",
                    }
                ],
            }
        )
    return threads


def delete_thread(user_id: int, person_slug: str) -> int:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM user_person_chat_messages
                WHERE user_id = %s AND person_slug = %s;
                """,
                (user_id, person_slug),
            )
            deleted = cur.rowcount
        conn.commit()
        return deleted
    finally:
        conn.close()


def list_user_media_files(user_id: int, *, limit: int = 300) -> list[dict[str, Any]]:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, person_slug, attachments, created_at
                FROM user_person_chat_messages
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
                    "source": "person_chat",
                    "message_id": row.get("id"),
                    "person_slug": row.get("person_slug"),
                    "created_at": row.get("created_at"),
                    "file": a,
                }
            )
    return items


def insert_message(
    user_id: int,
    person_slug: str,
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
                INSERT INTO user_person_chat_messages (
                    user_id, person_slug, role, content, attachments
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, role, content, attachments, created_at;
                """,
                (user_id, person_slug, role, content, Json(attachments or [])),
            )
            row = dict(cur.fetchone())
        conn.commit()
        return row
    finally:
        conn.close()


def _rag_context(person_slug: str, query: str, top_k: int) -> str:
    results = search_chunks(query, person_slug=person_slug, top_k=top_k)
    context = format_context(results)
    if not context.strip():
        return "（知識庫未檢索到相關資料）"
    return context


def generate_reply(
    *,
    person: dict[str, Any],
    history: list[dict[str, Any]],
    user_text: str,
    attachments: list[dict[str, Any]],
    client: Any,
    model: str,
    top_k: int = 10,
) -> str:
    slug = person.get("slug") or ""
    name_zh = person.get("name_zh") or slug
    bio = (person.get("bio") or "").strip()
    att_ctx = twin_chat._attachment_context(attachments)
    query = (user_text or "").strip() or att_ctx or name_zh
    context = _rag_context(slug, query, top_k)

    system = (
        f"你是{name_zh}的數位分身。"
        f"{bio}\n\n"
        "你正在與使用者一對一私聊，請以本人慣用的思考方式回應。"
        "若使用者上傳圖片或檔案，請根據內容回應。"
        "優先依據【參考資料】作答；資料不足時可合理推論並簡短說明。"
        "繁體中文，語氣自然，約 80～200 字，直接回答不要前言贅述。"
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": f"{system}\n\n【參考資料】\n{context}"}
    ]

    for msg in history[-MAX_HISTORY:]:
        role = "assistant" if msg.get("role") == "assistant" else "user"
        text = (msg.get("content") or "").strip()
        hist_att = twin_chat._attachment_context(msg.get("attachments") or [])
        if hist_att:
            text = f"{text}\n\n{hist_att}".strip() if text else hist_att
        if text:
            messages.append({"role": role, "content": text})

    user_parts: list[Any] = []
    user_text = (user_text or "").strip()
    if user_text:
        user_parts.append({"type": "text", "text": user_text})
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

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.72,
        max_tokens=400,
    )
    return (resp.choices[0].message.content or "").strip() or "我在，請繼續說。"
