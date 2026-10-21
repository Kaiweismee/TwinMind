"""
為所有 chunks 產生 embedding

用法：
  ./venv/bin/python db/setup_pgvector.py
  ./venv/bin/python rag/embed_chunks.py
  ./venv/bin/python rag/embed_chunks.py --limit 50
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import BATCH_SIZE
from db import connect
from embedder import embed_texts, embedding_dimension
from store import MODE_JSON, MODE_PGVECTOR, detect_storage_mode


def count_pending(cur, mode: str) -> int:
    if mode == MODE_PGVECTOR:
        cur.execute("SELECT COUNT(*) FROM chunks WHERE embedding IS NULL;")
    else:
        cur.execute("SELECT COUNT(*) FROM chunks WHERE embedding_json IS NULL;")
    return cur.fetchone()[0]


def fetch_batch(cur, mode: str, limit: int) -> list[tuple[int, str]]:
    col = "embedding IS NULL" if mode == MODE_PGVECTOR else "embedding_json IS NULL"
    cur.execute(
        f"""
        SELECT id, content FROM chunks
        WHERE {col}
        ORDER BY id
        LIMIT %s;
        """,
        (limit,),
    )
    return [(r[0], r[1]) for r in cur.fetchall()]


def update_batch(cur, mode: str, rows: list[tuple[int, str]], vectors: list[list[float]]) -> None:
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


def ensure_pgvector_index(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL;")
        n = cur.fetchone()[0]
        if n < 10:
            return
        lists = max(10, min(100, n // 20))
        cur.execute("DROP INDEX IF EXISTS idx_chunks_embedding;")
        cur.execute(
            f"""
            CREATE INDEX idx_chunks_embedding
            ON chunks USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = {lists});
            """
        )
    conn.commit()
    print(f"✓ pgvector 索引已建立（lists={lists}）。")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="只處理 N 筆（0=全部）")
    parser.add_argument("--no-index", action="store_true")
    args = parser.parse_args()

    conn = connect()
    mode = detect_storage_mode(conn)
    print(f"儲存模式：{mode}｜向量維度：{embedding_dimension()}\n")

    total_done = 0
    try:
        with conn.cursor() as cur:
            pending = count_pending(cur, mode)
            print(f"待處理：{pending} 個 chunks\n")
            if pending == 0:
                print("已全部完成。")
                return

        while True:
            batch_limit = BATCH_SIZE
            if args.limit:
                remaining = args.limit - total_done
                if remaining <= 0:
                    break
                batch_limit = min(batch_limit, remaining)

            with conn.cursor() as cur:
                batch = fetch_batch(cur, mode, batch_limit)
                if not batch:
                    break
                vectors = embed_texts([t for _, t in batch])
                update_batch(cur, mode, batch, vectors)
                conn.commit()

            total_done += len(batch)
            print(f"  已處理 {total_done} …")
            if args.limit and total_done >= args.limit:
                break

        print(f"\n完成，本輪 embedding {total_done} 筆。")
        if mode == MODE_PGVECTOR and not args.no_index and total_done:
            ensure_pgvector_index(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
