"""
以 OpenAI + 爬蟲向量庫（RAG）評估名人與討論主題的契合度。

流程：
1. 用主題對每位名人的 chunks 做語意檢索（代表其爬蟲資料庫）
2. 將 bio + 檢索段落送給 LLM 批次打分（0–100）與高／中／低
3. 失敗或未設定 API key 時由 topic_fit.py 退回關鍵字規則
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from data.person_profiles import PERSON_PROFILES, category_for_slug

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from topic_fit import (
    TIER_ORDER,
    debate_rounds_from_fit,
    enrich_person_with_fit,
    fit_tier,
    fit_tier_label,
    rank_persons_keyword_only as rank_persons_keyword,
    score_person_topic_fit,
)

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, dict[str, dict[str, Any]]]] = {}
_CACHE_TTL_SEC = int(os.getenv("TOPIC_FIT_CACHE_TTL", "1800"))
_BATCH_SIZE = max(1, int(os.getenv("TOPIC_FIT_LLM_BATCH", "8")))
_LLM_CANDIDATES = int(os.getenv("TOPIC_FIT_LLM_CANDIDATES", "18"))
_LLM_SCORE_MAX = int(os.getenv("TOPIC_FIT_LLM_SCORE_MAX", "18"))
_LLM_WORKERS = max(1, int(os.getenv("TOPIC_FIT_LLM_WORKERS", "3")))
_RAG_TOP_K = int(os.getenv("TOPIC_FIT_RAG_TOP_K", "3"))
_SNIPPET_MAX = int(os.getenv("TOPIC_FIT_SNIPPET_CHARS", "700"))
_LLM_PREFILTER = (os.getenv("TOPIC_FIT_LLM_PREFILTER") or "keyword").strip().lower()
_LLM_USE_VECTOR = os.getenv("TOPIC_FIT_LLM_USE_VECTOR", "1").strip().lower() not in (
    "0",
    "false",
    "no",
)
_LLM_POOL = ThreadPoolExecutor(max_workers=_LLM_WORKERS, thread_name_prefix="topic_fit_llm")
_EXCERPT_CACHE: dict[str, tuple[float, dict[str, str]]] = {}


def openai_configured() -> bool:
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    return bool(key) and not key.startswith("sk-your")


def _cache_key(topic: str, slugs: tuple[str, ...]) -> str:
    return f"{topic.strip().lower()}|{','.join(sorted(slugs))}"


def _get_cached(topic: str, slugs: tuple[str, ...]) -> dict[str, dict[str, Any]] | None:
    key = _cache_key(topic, slugs)
    row = _CACHE.get(key)
    if not row:
        return None
    expires, data = row
    if time.time() > expires:
        _CACHE.pop(key, None)
        return None
    return data


def _set_cache(topic: str, slugs: tuple[str, ...], data: dict[str, dict[str, Any]]) -> None:
    key = _cache_key(topic, slugs)
    _CACHE[key] = (time.time() + _CACHE_TTL_SEC, data)


def _person_bio(person: dict[str, Any]) -> str:
    slug = str(person.get("slug") or "")
    bio = (person.get("bio") or "").strip()
    prof = PERSON_PROFILES.get(slug)
    if prof and prof.get("bio"):
        bio = f"{bio} {prof['bio']}".strip()
    cat = person.get("category") or category_for_slug(slug)
    name = f"{person.get('name_zh') or ''} / {person.get('name_en') or ''}".strip()
    return f"姓名：{name}\n領域：{cat}\n簡介：{bio or '（無）'}"


def _excerpt_cache_get(topic: str, slugs: tuple[str, ...]) -> dict[str, str] | None:
    key = f"{topic.strip().lower()}|{','.join(sorted(slugs))}"
    row = _EXCERPT_CACHE.get(key)
    if not row:
        return None
    expires, data = row
    if time.time() > expires:
        _EXCERPT_CACHE.pop(key, None)
        return None
    return data


def _excerpt_cache_set(topic: str, slugs: tuple[str, ...], data: dict[str, str]) -> None:
    key = f"{topic.strip().lower()}|{','.join(sorted(slugs))}"
    _EXCERPT_CACHE[key] = (time.time() + _CACHE_TTL_SEC, data)


def prefetch_rag_excerpts(topic: str, slugs: list[str]) -> dict[str, str]:
    """批次語意檢索：主題只 embed 一次、DB 只查一次。"""
    topic = (topic or "").strip()
    clean = [s for s in slugs if s]
    if not topic or not clean:
        return {}

    slug_key = tuple(sorted(set(clean)))
    cached = _excerpt_cache_get(topic, slug_key)
    if cached is not None:
        return cached

    out: dict[str, str] = {s: "" for s in clean}
    if _LLM_USE_VECTOR:
        try:
            from rag.search import batch_search_chunks, format_context

            hits_map = batch_search_chunks(topic, clean, top_k=_RAG_TOP_K)
            for slug, hits in hits_map.items():
                if hits:
                    out[slug] = format_context(hits, max_chars=_SNIPPET_MAX)
        except Exception as exc:
            logger.debug("batch RAG excerpts failed: %s", exc)

    for slug in clean:
        if out.get(slug):
            continue
        db = _db_excerpts(topic, slug)
        if db:
            out[slug] = db[:_SNIPPET_MAX]

    _excerpt_cache_set(topic, slug_key, out)
    return out


def _rag_excerpts(topic: str, slug: str, excerpt_map: dict[str, str] | None = None) -> str:
    if excerpt_map is not None and slug in excerpt_map:
        return excerpt_map[slug]
    return prefetch_rag_excerpts(topic, [slug]).get(slug, "")


def _db_excerpts(topic: str, slug: str, limit: int = 4) -> str:
    """向量不可用時，用主題詞在 chunks 內容做文字匹配取樣。"""
    from rag.db import connect_dict

    terms = [t for t in re.split(r"[\s,，、]+", (topic or "").strip()) if len(t) >= 2][:6]
    if not terms:
        return ""

    conn, RealDictCursor = connect_dict()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            patterns = [f"%{t}%" for t in terms]
            cur.execute(
                """
                SELECT c.content, d.title, d.source_type
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                JOIN persons p ON p.id = c.person_id
                WHERE p.slug = %s
                  AND (
                    c.content ILIKE ANY(%s)
                    OR d.title ILIKE ANY(%s)
                  )
                ORDER BY LENGTH(c.content) DESC
                LIMIT %s;
                """,
                (slug, patterns, patterns, limit),
            )
            rows = cur.fetchall()
            if not rows:
                cur.execute(
                    """
                    SELECT c.content, d.title, d.source_type
                    FROM chunks c
                    JOIN documents d ON d.id = c.document_id
                    JOIN persons p ON p.id = c.person_id
                    WHERE p.slug = %s
                    ORDER BY c.id DESC
                    LIMIT %s;
                    """,
                    (slug, limit),
                )
                rows = cur.fetchall()
    finally:
        conn.close()

    parts: list[str] = []
    used = 0
    for i, r in enumerate(rows, 1):
        block = (
            f"[{i}] （{r.get('source_type') or 'doc'}｜{r.get('title') or ''}）\n"
            f"{(r.get('content') or '')[:400]}\n"
        )
        if used + len(block) > _SNIPPET_MAX:
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts)


def build_person_corpus_summary(
    topic: str,
    person: dict[str, Any],
    *,
    excerpt_map: dict[str, str] | None = None,
) -> str:
    slug = str(person.get("slug") or "")
    corpus = "【爬蟲資料】尚無可用段落（僅能依簡介判斷）"
    if _LLM_USE_VECTOR:
        rag = _rag_excerpts(topic, slug, excerpt_map)
        if rag:
            corpus = f"【與主題相關的爬蟲資料（語意檢索）】\n{rag}"
    if corpus.startswith("【爬蟲"):
        db = _db_excerpts(topic, slug)
        if db:
            corpus = f"【爬蟲資料取樣】\n{db}"
    docs = person.get("doc_count") or 0
    chunks = person.get("chunk_count") or 0
    return f"{_person_bio(person)}\n資料量：{docs} 篇文件 / {chunks} 個分塊\n{corpus}"


def _parse_llm_scores(raw: str) -> list[dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return []
        data = json.loads(m.group(0))

    if isinstance(data, dict):
        for key in ("scores", "persons", "results", "data"):
            if isinstance(data.get(key), list):
                return data[key]
        if "slug" in data:
            return [data]
    if isinstance(data, list):
        return data
    return []


def _normalize_score_item(item: dict[str, Any]) -> dict[str, Any] | None:
    slug = str(item.get("slug") or "").strip()
    if not slug:
        return None
    try:
        score = int(round(float(item.get("score", 50))))
    except (TypeError, ValueError):
        score = 50
    score = max(0, min(100, score))
    tier = str(item.get("tier") or fit_tier(score)).lower()
    if tier not in ("high", "mid", "low"):
        tier = fit_tier(score)
    reason = str(item.get("reason") or item.get("summary") or "").strip()
    return {
        "slug": slug,
        "topic_fit_score": score,
        "fit_tier": tier,
        "fit_tier_label": fit_tier_label(tier),
        "topic_fit_label": fit_tier_label(tier),
        "debate_rounds": debate_rounds_from_fit(score),
        "fit_reason": reason[:200],
        "fit_source": "llm",
    }


def _llm_score_batch(
    topic: str,
    persons: list[dict[str, Any]],
    *,
    excerpt_map: dict[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)

    blocks: list[str] = []
    for i, p in enumerate(persons, 1):
        slug = p.get("slug") or ""
        blocks.append(
            f"### 名人 {i}（slug: {slug}）\n"
            f"{build_person_corpus_summary(topic, p, excerpt_map=excerpt_map)}\n"
        )

    system = (
        "你是數位分身平台的策展人。根據每位名人的簡介與其爬蟲資料庫中與討論主題相關的段落，"
        "評估他們參與該主題討論的契合度。"
        "分數 0–100：≥78 高契合(high)、52–77 中(mid)、<52 低(low)。"
        "理由請用繁體中文一句話。僅輸出 JSON，格式："
        '{"scores":[{"slug":"...","score":0-100,"tier":"high|mid|low","reason":"..."}]}'
    )
    user = f"討論主題：{topic}\n\n" + "\n".join(blocks)

    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    raw = resp.choices[0].message.content or ""
    out: dict[str, dict[str, Any]] = {}
    for item in _parse_llm_scores(raw):
        norm = _normalize_score_item(item)
        if norm:
            out[norm["slug"]] = norm
    return out


def score_persons_with_llm(
    topic: str,
    persons: list[dict[str, Any]],
    *,
    prefilter: list[dict[str, Any]] | None = None,
    score_cap: int | None = None,
) -> dict[str, dict[str, Any]]:
    """回傳 slug → 契合度欄位（含 fit_source=llm）；僅對前 N 名候選人呼叫 OpenAI。"""
    topic = (topic or "").strip()
    if not topic or not persons:
        return {}

    slugs = tuple(sorted(str(p.get("slug") or "") for p in persons if p.get("slug")))
    cached = _get_cached(topic, slugs)
    if cached is not None:
        return cached

    cap = score_cap if score_cap is not None else _LLM_SCORE_MAX
    if cap <= 0:
        cap = _LLM_SCORE_MAX
    candidates = prefilter if prefilter is not None else persons
    if cap > 0 and len(candidates) > cap:
        candidates = candidates[:cap]

    slug_list = [str(p.get("slug") or "") for p in candidates if p.get("slug")]
    excerpt_map = prefetch_rag_excerpts(topic, slug_list)

    merged: dict[str, dict[str, Any]] = {}
    batches = [
        candidates[i : i + _BATCH_SIZE]
        for i in range(0, len(candidates), _BATCH_SIZE)
    ]
    if len(batches) <= 1:
        for batch in batches:
            merged.update(_llm_score_batch(topic, batch, excerpt_map=excerpt_map))
    else:
        futures = [
            _LLM_POOL.submit(
                _llm_score_batch, topic, batch, excerpt_map=excerpt_map
            )
            for batch in batches
        ]
        for fut in as_completed(futures):
            try:
                merged.update(fut.result())
            except Exception as exc:
                logger.warning("LLM batch failed: %s", exc)

    _set_cache(topic, slugs, merged)
    return merged


def _hybrid_scores_for_persons(
    topic: str, persons: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    try:
        from topic_fit_semantic import score_persons_hybrid

        return score_persons_hybrid(topic, persons)
    except Exception as exc:
        logger.debug("hybrid scores unavailable: %s", exc)
        return {}


def apply_llm_fit_to_person(
    topic: str,
    person: dict[str, Any],
    scores: dict[str, dict[str, Any]],
    hybrid_scores: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    slug = str(person.get("slug") or "")
    fit = scores.get(slug)
    if fit:
        return {**person, **fit}
    if hybrid_scores and slug in hybrid_scores:
        row = {**person, **hybrid_scores[slug]}
        row["fit_source"] = hybrid_scores[slug].get("fit_source", "hybrid")
        return row
    row = enrich_person_with_fit(topic, person)
    row["fit_source"] = row.get("fit_source", "keyword")
    return row


def _llm_prefilter(
    topic: str,
    persons: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    cap = max(limit, _LLM_CANDIDATES, len(persons))
    if _LLM_PREFILTER in ("semantic", "hybrid", "vector", "rag"):
        try:
            from topic_fit_semantic import rank_persons_for_topic_semantic

            return rank_persons_for_topic_semantic(topic, persons, limit=cap)
        except Exception as exc:
            logger.warning("LLM semantic prefilter failed: %s", exc)
    return rank_persons_keyword(topic, persons, limit=cap)


def rank_persons_for_topic_llm(
    topic: str,
    persons: list[dict[str, Any]],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    topic = (topic or "").strip()
    if not topic:
        return []

    if not openai_configured():
        raise RuntimeError("未設定 OPENAI_API_KEY，無法使用 AI 推薦")

    hybrid_scores = _hybrid_scores_for_persons(topic, persons)
    prefilter_cap = max(limit, _LLM_CANDIDATES) if limit else _LLM_CANDIDATES
    if hybrid_scores:
        prefilter = sorted(
            persons,
            key=lambda p: (
                -int((hybrid_scores.get(str(p.get("slug") or "")) or {}).get("topic_fit_score") or 0),
                p.get("name_zh") or p.get("slug") or "",
            ),
        )[:prefilter_cap]
    else:
        prefilter = _llm_prefilter(topic, persons, limit=prefilter_cap)
    llm_cap = min(_LLM_SCORE_MAX, len(prefilter)) if _LLM_SCORE_MAX > 0 else len(prefilter)
    scores = score_persons_with_llm(
        topic, persons, prefilter=prefilter, score_cap=llm_cap
    )
    enriched = [
        apply_llm_fit_to_person(topic, p, scores, hybrid_scores) for p in persons
    ]
    enriched.sort(
        key=lambda x: (
            TIER_ORDER.get(x.get("fit_tier") or "low", 9),
            -int(x.get("topic_fit_score") or 0),
            x.get("name_zh") or x.get("slug") or "",
        )
    )
    return enriched[: max(1, limit)]


def build_member_fit_plan_llm(
    topic: str,
    slugs: list[str],
    persons_by_slug: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    persons = [persons_by_slug.get(s) or {"slug": s, "name_zh": s} for s in slugs]
    hybrid_scores = _hybrid_scores_for_persons(topic, persons)
    scores = score_persons_with_llm(
        topic, persons, prefilter=persons, score_cap=len(persons)
    )
    rows: list[dict[str, Any]] = []
    for slug in slugs:
        base = persons_by_slug.get(slug) or {"slug": slug, "name_zh": slug}
        row = apply_llm_fit_to_person(topic, base, scores, hybrid_scores)
        row["person_slug"] = slug
        rows.append(row)
    rows.sort(key=lambda x: (-int(x.get("topic_fit_score") or 0), x.get("name_zh") or ""))
    for i, row in enumerate(rows):
        row["sort_order"] = i
    return rows
