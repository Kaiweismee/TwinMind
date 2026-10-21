"""爬蟲共用：寫入 documents / chunks"""

from __future__ import annotations

import hashlib
import json
import re
import textwrap
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "digital_twin",
    "user": "kaiwei",
}

CHUNK_SIZE = 400


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def split_chunks(text: str, size: int = CHUNK_SIZE) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    return textwrap.wrap(text, width=size, break_long_words=False, break_on_hyphens=False)


def get_person_id(cur, slug: str) -> int:
    cur.execute("SELECT id FROM persons WHERE slug = %s;", (slug,))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"找不到名人 slug={slug}，請先執行 db/schema.sql")
    return row["id"]


def save_document_and_chunks(
    cur,
    person_id: int,
    source_url: str,
    title: str,
    raw_content: str,
    language: str,
    metadata: dict[str, Any],
    source_type: str = "wiki",
) -> tuple[int, int]:
    h = content_hash(raw_content)

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
        (person_id, source_url, title, source_type, language, raw_content, h),
    )
    document_id = cur.fetchone()["id"]

    cur.execute("DELETE FROM chunks WHERE document_id = %s;", (document_id,))

    parts = split_chunks(raw_content)
    if not parts:
        parts = [raw_content]

    for idx, part in enumerate(parts):
        cur.execute(
            """
            INSERT INTO chunks (document_id, person_id, chunk_index, content, metadata)
            VALUES (%s, %s, %s, %s, %s);
            """,
            (
                document_id,
                person_id,
                idx,
                part,
                json.dumps({**metadata, "chunk_chars": len(part)}, ensure_ascii=False),
            ),
        )

    return document_id, len(parts)


def print_stats(conn) -> None:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
                p.name_zh,
                COUNT(DISTINCT d.id) AS docs,
                COUNT(DISTINCT c.id) AS chunks
            FROM persons p
            LEFT JOIN documents d ON d.person_id = p.id
            LEFT JOIN chunks c ON c.person_id = p.id
            GROUP BY p.id, p.name_zh
            ORDER BY p.id;
            """
        )
        print("--- 資料庫統計 ---")
        for row in cur.fetchall():
            print(f"  {row['name_zh']}: {row['docs']} 篇文件, {row['chunks']} 個 chunks")
