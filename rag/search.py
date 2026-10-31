"""
語意搜尋：依名人 + 問題，從 chunks 找最相關段落
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from config import DEFAULT_TOP_K, RAG_MAX_CHUNKS, RAG_MIN_SIMILARITY
from db import connect
from embedder import embed_texts
from store import MODE_JSON, MODE_PGVECTOR, detect_storage_mode

_QUERY_EMBED_CACHE: dict[str, tuple[float, list[float]]] = {}
_QUERY_EMBED_TTL = int(__import__("os").getenv("RAG_QUERY_EMBED_TTL", "300"))


def embed_query_cached(query: str) -> list[float]:
    """同一主題多次檢索時重用 embedding（契合度分析會重複用到）。"""
    key = (query or "").strip()
    if not key:
        return embed_texts([""])[0]
    row = _QUERY_EMBED_CACHE.get(key)
    if row and time.time() < row[0]:
        return row[1]
    vec = embed_texts([key])[0]
    _QUERY_EMBED_CACHE[key] = (time.time() + _QUERY_EMBED_TTL, vec)
    return vec


def _fetch_limit(top_k: int) -> int:
    """top_k <= 0 表示不固定筆數，改拉較多候選再依相似度過濾。"""
    if top_k > 0:
        return top_k
    return max(RAG_MAX_CHUNKS, 1)


def _apply_top_k(results: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    if top_k > 0:
        return results[:top_k]
    filtered = [
        r for r in results
        if float(r.get("similarity") or 0) >= RAG_MIN_SIMILARITY
    ]
    return filtered if filtered else results


def _cosine_similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    q = query / (np.linalg.norm(query) + 1e-9)
    m = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
    return m @ q


def search_chunks_pgvector(
    query_vec: list[float],
    person_slug: str,
    top_k: int,
    source_types: list[str] | None,
) -> list[dict[str, Any]]:
    limit = _fetch_limit(top_k)
    type_filter = ""
    params: list[Any] = [query_vec, person_slug, query_vec, limit]
    if source_types:
        type_filter = "AND d.source_type = ANY(%s)"
        params = [query_vec, person_slug, source_types, query_vec, limit]

    sql = f"""
        SELECT
            c.id AS chunk_id,
            c.content,
            c.chunk_index,
            1 - (c.embedding <=> %s::vector) AS similarity,
            d.title,
            d.source_url,
            d.source_type,
            p.name_zh
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        JOIN persons p ON p.id = c.person_id
        WHERE p.slug = %s
          AND c.embedding IS NOT NULL
          {type_filter}
        ORDER BY c.embedding <=> %s::vector
        LIMIT %s;
    """
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
            return _apply_top_k(rows, top_k)
    finally:
        conn.close()


def search_chunks_json(
    query_vec: list[float],
    person_slug: str,
    top_k: int,
    source_types: list[str] | None,
) -> list[dict[str, Any]]:
    type_sql = ""
    params: list[Any] = [person_slug]
    if source_types:
        type_sql = "AND d.source_type = ANY(%s)"
        params.append(source_types)

    sql = f"""
        SELECT
            c.id AS chunk_id,
            c.content,
            c.chunk_index,
            c.embedding_json,
            d.title,
            d.source_url,
            d.source_type,
            p.name_zh
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        JOIN persons p ON p.id = c.person_id
        WHERE p.slug = %s
          AND c.embedding_json IS NOT NULL
          {type_sql};
    """
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]

        if not rows:
            return []

        q = np.array(query_vec, dtype=np.float32)
        ids, texts, meta, vectors = [], [], [], []
        for row in rows:
            r = dict(zip(cols, row))
            vec = r.pop("embedding_json")
            if isinstance(vec, str):
                vec = json.loads(vec)
            ids.append(r["chunk_id"])
            texts.append(r)
            vectors.append(vec)

        mat = np.array(vectors, dtype=np.float32)
        scores = _cosine_similarity(q, mat)
        limit = _fetch_limit(top_k)
        order = np.argsort(-scores)[:limit]

        results = []
        for idx in order:
            item = texts[idx].copy()
            item["similarity"] = float(scores[idx])
            results.append(item)
        return _apply_top_k(results, top_k)
    finally:
        conn.close()


def batch_search_chunks_pgvector(
    query_vec: list[float],
    person_slugs: list[str],
    top_k: int,
    source_types: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """一次 SQL 取得多位名人的 top-k 語意段落（契合度批次用）。"""
    slugs = [s for s in person_slugs if s]
    if not slugs:
        return {}

    limit = _fetch_limit(top_k)
    type_filter = ""
    params: list[Any] = [query_vec, slugs, query_vec, limit]
    if source_types:
        type_filter = "AND d.source_type = ANY(%s)"
        params = [query_vec, slugs, source_types, query_vec, limit]

    sql = f"""
        WITH ranked AS (
            SELECT
                p.slug,
                c.id AS chunk_id,
                c.content,
                c.chunk_index,
                1 - (c.embedding <=> %s::vector) AS similarity,
                d.title,
                d.source_url,
                d.source_type,
                p.name_zh,
                ROW_NUMBER() OVER (
                    PARTITION BY p.slug
                    ORDER BY c.embedding <=> %s::vector
                ) AS rn
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            JOIN persons p ON p.id = c.person_id
            WHERE p.slug = ANY(%s)
              AND c.embedding IS NOT NULL
              {type_filter}
        )
        SELECT
            slug, chunk_id, content, chunk_index, similarity,
            title, source_url, source_type, name_zh
        FROM ranked
        WHERE rn <= %s
        ORDER BY slug, similarity DESC;
    """
    conn = connect()
    out: dict[str, list[dict[str, Any]]] = {s: [] for s in slugs}
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description]
            for row in cur.fetchall():
                r = dict(zip(cols, row))
                slug = str(r.pop("slug", ""))
                if slug in out:
                    out[slug].append(r)
    finally:
        conn.close()

    for slug in out:
        out[slug] = _apply_top_k(out[slug], top_k)
    return out


def batch_search_chunks(
    query: str,
    person_slugs: list[str],
    top_k: int = DEFAULT_TOP_K,
    source_types: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """多位名人一次 embedding + 查詢（pgvector 模式）。"""
    slugs = [s for s in person_slugs if s]
    if not slugs:
        return {}

    query_vec = embed_query_cached(query)
    conn = connect()
    try:
        mode = detect_storage_mode(conn)
    finally:
        conn.close()

    if mode == MODE_PGVECTOR:
        return batch_search_chunks_pgvector(
            query_vec, slugs, top_k, source_types
        )

    return {
        slug: search_chunks_json(query_vec, slug, top_k, source_types)
        for slug in slugs
    }


def search_chunks(
    query: str,
    person_slug: str,
    top_k: int = DEFAULT_TOP_K,
    source_types: list[str] | None = None,
    *,
    query_vec: list[float] | None = None,
) -> list[dict[str, Any]]:
    from config import EMBEDDING_BACKEND

    if query_vec is None:
        query_vec = embed_query_cached(query)
    if EMBEDDING_BACKEND == "tfidf":
        return search_chunks_json(query_vec, person_slug, top_k, source_types)

    conn = connect()
    try:
        mode = detect_storage_mode(conn)
    finally:
        conn.close()

    if mode == MODE_PGVECTOR:
        return search_chunks_pgvector(query_vec, person_slug, top_k, source_types)
    return search_chunks_json(query_vec, person_slug, top_k, source_types)


def rank_persons_by_topic_pgvector(
    query_vec: list[float],
    *,
    chunk_pool: int = 500,
    min_similarity: float | None = None,
) -> list[dict[str, Any]]:
    """
    跨所有名人 chunks 語意檢索，依每位名人與主題最相關的爬蟲段落排序。
    分數：0.65 * best_chunk_sim + 0.35 * avg(top3 chunk sim)
    """
    min_sim = RAG_MIN_SIMILARITY if min_similarity is None else min_similarity
    pool = max(50, min(chunk_pool, 2000))
    sql = """
        WITH hits AS (
            SELECT
                p.slug,
                p.name_zh,
                1 - (c.embedding <=> %s::vector) AS similarity
            FROM chunks c
            JOIN persons p ON p.id = c.person_id
            WHERE c.embedding IS NOT NULL
              AND p.slug !~ '^user_'
            ORDER BY c.embedding <=> %s::vector
            LIMIT %s
        ),
        ranked AS (
            SELECT
                slug,
                name_zh,
                similarity,
                ROW_NUMBER() OVER (
                    PARTITION BY slug ORDER BY similarity DESC
                ) AS rn
            FROM hits
        )
        SELECT
            slug,
            MAX(similarity) AS best_sim,
            AVG(similarity) FILTER (WHERE rn <= 3) AS avg_top3,
            COUNT(*) FILTER (WHERE rn <= 3) AS hit_chunks
        FROM ranked
        WHERE similarity >= %s
        GROUP BY slug, name_zh
        ORDER BY best_sim DESC, avg_top3 DESC NULLS LAST, slug
    """
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (query_vec, query_vec, pool, min_sim),
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()

    out: list[dict[str, Any]] = []
    for r in rows:
        best = float(r.get("best_sim") or 0)
        avg3 = float(r.get("avg_top3") or best)
        combined = 0.65 * best + 0.35 * avg3
        out.append(
            {
                "slug": r["slug"],
                "name_zh": r.get("name_zh"),
                "best_similarity": best,
                "avg_top3_similarity": avg3,
                "combined_similarity": combined,
                "hit_chunks": int(r.get("hit_chunks") or 0),
            }
        )
    return out


def rank_persons_by_topic_json(
    query_vec: list[float],
    *,
    chunk_pool: int = 800,
    min_similarity: float | None = None,
) -> list[dict[str, Any]]:
    """JSONB 向量備援：載入有 embedding 的 chunks 後在記憶體聚合（較慢）。"""
    min_sim = RAG_MIN_SIMILARITY if min_similarity is None else min_similarity
    sql = """
        SELECT
            p.slug,
            p.name_zh,
            c.embedding_json
        FROM chunks c
        JOIN persons p ON p.id = c.person_id
        WHERE c.embedding_json IS NOT NULL
          AND p.slug !~ '^user_'
        ORDER BY c.id DESC
        LIMIT %s;
    """
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (max(chunk_pool, 100),))
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
    finally:
        conn.close()

    if not rows:
        return []

    q = np.array(query_vec, dtype=np.float32)
    per_slug: dict[str, list[float]] = {}
    names: dict[str, str] = {}
    for row in rows:
        r = dict(zip(cols, row))
        slug = r["slug"]
        vec = r["embedding_json"]
        if isinstance(vec, str):
            vec = json.loads(vec)
        v = np.array(vec, dtype=np.float32)
        qn = q / (np.linalg.norm(q) + 1e-9)
        vn = v / (np.linalg.norm(v) + 1e-9)
        sim = float(np.dot(qn, vn))
        if sim < min_sim:
            continue
        per_slug.setdefault(slug, []).append(sim)
        names[slug] = r.get("name_zh") or slug

    ranked: list[dict[str, Any]] = []
    for slug, sims in per_slug.items():
        sims.sort(reverse=True)
        best = sims[0]
        top3 = sims[:3]
        avg3 = sum(top3) / len(top3)
        combined = 0.65 * best + 0.35 * avg3
        ranked.append(
            {
                "slug": slug,
                "name_zh": names.get(slug),
                "best_similarity": best,
                "avg_top3_similarity": avg3,
                "combined_similarity": combined,
                "hit_chunks": len(top3),
            }
        )
    ranked.sort(
        key=lambda x: (-x["combined_similarity"], x.get("name_zh") or x["slug"])
    )
    return ranked


def rank_persons_by_topic(
    query: str,
    *,
    chunk_pool: int = 500,
    min_similarity: float | None = None,
    query_vec: list[float] | None = None,
) -> list[dict[str, Any]]:
    """
    依討論主題，用爬蟲向量庫為所有名人排序（推薦用此函式，不需逐人 LLM）。
    """
    if query_vec is None:
        query_vec = embed_query_cached(query)
    conn = connect()
    try:
        mode = detect_storage_mode(conn)
    finally:
        conn.close()

    if mode == MODE_PGVECTOR:
        return rank_persons_by_topic_pgvector(
            query_vec, chunk_pool=chunk_pool, min_similarity=min_similarity
        )
    return rank_persons_by_topic_json(
        query_vec, chunk_pool=chunk_pool, min_similarity=min_similarity
    )


def corpus_similarity_available() -> bool:
    """是否已有可向量化檢索的 chunks。"""
    conn = connect()
    try:
        mode = detect_storage_mode(conn)
        col = "embedding" if mode == MODE_PGVECTOR else "embedding_json"
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT 1 FROM chunks
                WHERE {col} IS NOT NULL
                LIMIT 1;
                """
            )
            return cur.fetchone() is not None
    except Exception:
        return False
    finally:
        conn.close()


def format_context(
    results: list[dict[str, Any]],
    max_chars: int = 6000,
    *,
    start_index: int = 1,
) -> str:
    parts: list[str] = []
    used = 0
    for i, r in enumerate(results, start_index):
        block = (
            f"[{i}] （相似度 {r['similarity']:.3f}｜{r['source_type']}｜{r['title']}）\n"
            f"{r['content']}\n"
            f"來源：{r['source_url']}\n"
        )
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts)
