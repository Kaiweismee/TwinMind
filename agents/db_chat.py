"""討論紀錄寫入 PostgreSQL"""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).parent.parent / "rag"))
from config import DB_CONFIG  # noqa: E402

ROLE_TO_SLUG = {
    "musk": "elon_musk",
    "jensen": "jensen_huang",
    "jobs": "steve_jobs",
    "gates": "bill_gates",
}


def _conn():
    return psycopg2.connect(**DB_CONFIG)


def create_session(topic: str) -> int:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_sessions (topic) VALUES (%s) RETURNING id;",
                (topic,),
            )
            session_id = cur.fetchone()[0]
        conn.commit()
        return session_id
    finally:
        conn.close()


def _person_id(cur, role: str) -> int | None:
    slug = ROLE_TO_SLUG.get(role)
    if not slug:
        return None
    cur.execute("SELECT id FROM persons WHERE slug = %s;", (slug,))
    row = cur.fetchone()
    return row[0] if row else None


def add_message(
    session_id: int,
    role: str,
    content: str,
    chunk_ids: list[int] | None = None,
) -> None:
    chunk_ids = chunk_ids or []
    conn = _conn()
    try:
        with conn.cursor() as cur:
            person_id = _person_id(cur, role)
            cur.execute(
                """
                INSERT INTO chat_messages (
                    session_id, person_id, role, content, retrieved_chunk_ids
                ) VALUES (%s, %s, %s, %s, %s);
                """,
                (session_id, person_id, role, content.strip(), chunk_ids),
            )
        conn.commit()
    finally:
        conn.close()


def end_session(session_id: int, summary: str | None = None) -> None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE chat_sessions
                SET ended_at = NOW(), summary = %s
                WHERE id = %s;
                """,
                (summary, session_id),
            )
        conn.commit()
    finally:
        conn.close()
