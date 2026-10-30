"""使用者分身 RAG：分身對話與上傳內容 → chunks + embedding → person_slug=user_{id}"""

from __future__ import annotations

import json
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


from web.core.rag_backend import connect
from crawl.db_utils import content_hash, split_chunks
from web.core.rag_backend import embed_texts
from web.core.rag_backend import format_context, search_chunks
from web.core.rag_backend import MODE_JSON, MODE_PGVECTOR, detect_storage_mode


def user_person_slug(user_id: int) -> str:
    return f"user_{user_id}"


def is_user_person_slug(slug: str) -> bool:
    return (slug or "").startswith("user_")


def _conn():
    return connect()


def ensure_user_person(
    user_id: int,
    *,
    display_name: str,
    bio: str = "",
) -> str:
    """在 persons 表建立使用者專屬知識庫（不顯示在名人探索）。"""
    slug = user_person_slug(user_id)
    name = (display_name or "使用者").strip() or "使用者"
    person_bio = (bio or "").strip() or f"{name} 透過分身對話與上傳資料建立的私人知識庫"
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO persons (slug, name_zh, name_en, bio, category)
                VALUES (%s, %s, %s, %s, 'user_private')
                ON CONFLICT (slug) DO UPDATE SET
                    name_zh = EXCLUDED.name_zh,
                    bio = EXCLUDED.bio,
                    category = 'user_private',
                    updated_at = NOW();
                """,
                (slug, f"{name}的資料", f"{name} private KB", person_bio),
            )
        conn.commit()
    finally:
        conn.close()
    return slug


def _get_person_id(cur, slug: str) -> int:
    cur.execute("SELECT id FROM persons WHERE slug = %s;", (slug,))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"找不到 person slug={slug}")
    return int(row[0])


def _embed_chunk_rows(cur, mode: str, rows: list[tuple[int, str]]) -> None:
    if not rows:
        return
    vectors = embed_texts([text for _, text in rows])
    for (chunk_id, _), vec in zip(rows, vectors):
        if mode == MODE_PGVECTOR:
            cur.execute(
                "UPDATE chunks SET embedding = %s WHERE id = %s;",
                (vec, chunk_id),
            )
        else:
            cur.execute(
                "UPDATE chunks SET embedding_json = %s WHERE id = %s;",
                (json.dumps(vec), chunk_id),
            )


def _save_and_embed_document(
    *,
    person_id: int,
    source_url: str,
    title: str,
    raw_content: str,
    source_type: str = "twin_chat",
    metadata: dict[str, Any] | None = None,
    language: str = "zh",
) -> list[int]:
    text = (raw_content or "").strip()
    if not text:
        return []

    meta = dict(metadata or {})
    conn = _conn()
    chunk_ids: list[int] = []
    try:
        mode = detect_storage_mode(conn)
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            h = content_hash(text)
            cur.execute(
                """
                INSERT INTO documents (
                    person_id, source_url, title, source_type, language,
                    raw_content, content_hash
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (person_id, source_url)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    raw_content = EXCLUDED.raw_content,
                    content_hash = EXCLUDED.content_hash,
                    scraped_at = NOW(),
                    updated_at = NOW()
                RETURNING id;
                """,
                (person_id, source_url, title, source_type, language, text, h),
            )
            document_id = cur.fetchone()["id"]
            cur.execute("DELETE FROM chunks WHERE document_id = %s;", (document_id,))

            parts = split_chunks(text)
            if not parts:
                parts = [text]

            embed_batch: list[tuple[int, str]] = []
            for idx, part in enumerate(parts):
                cur.execute(
                    """
                    INSERT INTO chunks (document_id, person_id, chunk_index, content, metadata)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id;
                    """,
                    (
                        document_id,
                        person_id,
                        idx,
                        part,
                        json.dumps(
                            {**meta, "chunk_chars": len(part)},
                            ensure_ascii=False,
                        ),
                    ),
                )
                cid = int(cur.fetchone()["id"])
                chunk_ids.append(cid)
                embed_batch.append((cid, part))

            _embed_chunk_rows(cur, mode, embed_batch)
        conn.commit()
    finally:
        conn.close()
    return chunk_ids


def _message_body(content: str, attachments: list[dict[str, Any]] | None) -> str:
    parts: list[str] = []
    text = (content or "").strip()
    if text:
        parts.append(text)
    for a in attachments or []:
        name = a.get("name") or "檔案"
        if a.get("text_preview"):
            parts.append(f"【檔案：{name}】\n{a['text_preview'][:4000]}")
        elif a.get("kind") == "image":
            parts.append(f"【圖片：{name}】使用者曾分享圖片。")
        else:
            parts.append(f"【檔案：{name}】使用者曾上傳檔案。")
    return "\n\n".join(parts).strip()


def ingest_twin_chat_message(
    user_id: int,
    twin_id: int,
    *,
    message_id: int,
    role: str,
    content: str,
    attachments: list[dict[str, Any]] | None = None,
    twin_name: str = "分身",
    display_name: str = "使用者",
) -> list[int]:
    """將一則分身對話寫入 user_{id} 知識庫（僅 user 角色）。"""
    if role != "user":
        return []
    body = _message_body(content, attachments)
    if not body:
        return []

    slug = ensure_user_person(user_id, display_name=display_name)
    conn = _conn()
    try:
        with conn.cursor() as cur:
            person_id = _get_person_id(cur, slug)
    finally:
        conn.close()

    source_url = f"twin-chat://user/{user_id}/twin/{twin_id}/message/{message_id}"
    title = f"與{twin_name}分身對話 #{message_id}"
    return _save_and_embed_document(
        person_id=person_id,
        source_url=source_url,
        title=title,
        raw_content=body,
        source_type="twin_chat",
        metadata={
            "user_id": user_id,
            "twin_id": twin_id,
            "message_id": message_id,
            "kind": "twin_chat_message",
        },
    )


def backfill_user_knowledge(
    user_id: int,
    *,
    display_name: str,
    twin_id: int | None = None,
) -> int:
    """將既有分身對話補進知識庫。回傳新增的 document 數。"""
    from web.conversations import twin_chat

    ensure_user_person(user_id, display_name=display_name)
    count = 0
    twin_ids: list[int] = []
    if twin_id:
        twin_ids = [twin_id]
    else:
        from web.repositories import user_store

        for t in user_store.list_user_twins(user_id):
            twin_ids.append(int(t["id"]))

    for tid in twin_ids:
        messages = twin_chat.list_messages(user_id, tid, limit=500)
        for msg in messages:
            if msg.get("role") != "user":
                continue
            ids = ingest_twin_chat_message(
                user_id,
                tid,
                message_id=int(msg["id"]),
                role="user",
                content=msg.get("content") or "",
                attachments=msg.get("attachments") or [],
                display_name=display_name,
            )
            if ids:
                count += 1
    return count


def ingest_session_attachment(
    user_id: int,
    session_id: int,
    *,
    topic: str,
    attachment: dict[str, Any],
    display_name: str = "使用者",
) -> list[int]:
    """將單一討論室參考檔寫入 user_{id} 知識庫（僅此聊天室來源）。"""
    body = _message_body("", [attachment])
    if not body:
        return []

    ensure_user_person(user_id, display_name=display_name)
    conn = _conn()
    try:
        with conn.cursor() as cur:
            person_id = _get_person_id(cur, user_person_slug(user_id))
    finally:
        conn.close()

    file_id = attachment.get("id") or attachment.get("stored_name") or "file"
    name = attachment.get("name") or "檔案"
    source_url = f"session://{session_id}/file/{file_id}"
    title = f"討論室 #{session_id} · {name}"
    raw = f"【討論主題】{topic}\n\n{body}"
    return _save_and_embed_document(
        person_id=person_id,
        source_url=source_url,
        title=title,
        raw_content=raw,
        source_type="session_context",
        metadata={
            "user_id": user_id,
            "session_id": session_id,
            "kind": "session_attachment",
            "file_name": name,
        },
    )


def search_session_context(
    user_id: int,
    session_id: int,
    query: str,
    top_k: int = 6,
) -> tuple[str, list[int], list[dict[str, Any]]]:
    """僅檢索此討論室上傳的參考檔。"""
    slug = user_person_slug(user_id)
    prefix = f"session://{session_id}/"
    pool = search_chunks(
        query,
        person_slug=slug,
        top_k=max(top_k * 4, 12),
        source_types=["session_context"],
    )
    filtered = [
        r for r in pool if str(r.get("source_url") or "").startswith(prefix)
    ][:top_k]
    context = format_context(filtered)
    chunk_ids = [int(r["chunk_id"]) for r in filtered]
    sources = []
    for r in filtered:
        text = r.get("content") or ""
        if len(text) > 2800:
            text = text[:2800] + "…"
        sources.append(
            {
                "chunk_id": int(r["chunk_id"]),
                "similarity": round(float(r.get("similarity") or 0), 4),
                "title": r.get("title"),
                "source_type": r.get("source_type") or "session_context",
                "source_url": r.get("source_url"),
                "content": text,
            }
        )
    return context, chunk_ids, sources


def search_user_context(
    user_id: int,
    query: str,
    top_k: int = 8,
) -> tuple[str, list[int], list[dict[str, Any]]]:
    """RAG 檢索使用者私人知識庫。"""
    slug = user_person_slug(user_id)
    results = search_chunks(query, person_slug=slug, top_k=top_k)
    context = format_context(results)
    if not context.strip():
        context = "（尚無與你相關的私人資料；可先在「訓練個人資料」分享更多資訊）"
    chunk_ids = [int(r["chunk_id"]) for r in results]
    sources = []
    for r in results:
        text = r.get("content") or ""
        if len(text) > 2800:
            text = text[:2800] + "…"
        sources.append(
            {
                "chunk_id": int(r["chunk_id"]),
                "similarity": round(float(r.get("similarity") or 0), 4),
                "title": r.get("title"),
                "source_type": r.get("source_type") or "twin_chat",
                "source_url": r.get("source_url"),
                "content": text,
            }
        )
    return context, chunk_ids, sources
