"""偵測向量儲存方式：pgvector 或 JSONB 備援"""

from __future__ import annotations

import psycopg2

from config import DB_CONFIG

MODE_PGVECTOR = "pgvector"
MODE_JSON = "json"


def detect_storage_mode(conn) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT a.attname, t.typname
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_type t ON t.oid = a.atttypid
            WHERE c.relname = 'chunks'
              AND a.attname IN ('embedding', 'embedding_json')
              AND NOT a.attisdropped;
            """
        )
        cols = {row[0]: row[1] for row in cur.fetchall()}

    if "embedding" in cols and cols["embedding"] == "vector":
        return MODE_PGVECTOR
    if "embedding_json" in cols:
        return MODE_JSON
    raise RuntimeError("chunks 表沒有 embedding 或 embedding_json 欄位，請先執行 setup。")


def setup_storage() -> str:
    """嘗試 pgvector，失敗則用 JSONB。回傳使用的模式。"""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                cur.execute(
                    "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding vector(384);"
                )
                conn.commit()
                print("  已启用：CREATE EXTENSION vector + chunks.embedding")
                return MODE_PGVECTOR
            except Exception as e:
                conn.rollback()
                print(f"  pgvector 不可用（{e}），改用 JSONB …")
                cur.execute(
                    "ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding_json JSONB;"
                )
                conn.commit()
                return MODE_JSON
    finally:
        conn.close()
