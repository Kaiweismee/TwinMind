"""
語意推薦：主題向量 × 全庫爬蟲 chunks（RAG），再與關鍵字規則混合。

比「純關鍵字」或「每位名人各 call 一次 LLM」更準、更快：
- 一次 embedding + 一條 SQL（或單次記憶體聚合）得到全員排序
- 分數來自真實資料相似度，而非手寫詞表
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any


from web.recommendations.topic_fit import TIER_ORDER, debate_rounds_from_fit, enrich_person_with_fit, fit_tier, fit_tier_label, score_person_topic_fit

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, dict[str, dict[str, Any]]]] = {}
_CACHE_TTL = int(os.getenv("TOPIC_FIT_CACHE_TTL", "1800"))
_SEMANTIC_WEIGHT = float(os.getenv("TOPIC_FIT_SEMANTIC_WEIGHT", "0.78"))
_KEYWORD_WEIGHT = float(os.getenv("TOPIC_FIT_KEYWORD_WEIGHT", "0.22"))
_CHUNK_POOL = int(os.getenv("TOPIC_FIT_CHUNK_POOL", "500"))
_MIN_COMBINED_SIM = float(os.getenv("TOPIC_FIT_MIN_SIM", "0.18"))


def corpus_ranking_available() -> bool:
    try:
        from web.core.rag_backend import corpus_similarity_available

        return corpus_similarity_available()
    except Exception as exc:
        logger.debug("corpus ranking unavailable: %s", exc)
        return False


def _sim_to_score(combined_sim: float) -> int:
    """將餘弦相似度映射到 0–100（針對 multilingual-MiniLM 實測區間調整）。"""
    # 典型：弱相關 ~0.2，強相關 ~0.55–0.75
    low, high = 0.18, 0.62
    if combined_sim <= low:
        return int(max(0, combined_sim / low * 35))
    if combined_sim >= high:
        return int(min(100, 78 + (combined_sim - high) / (1.0 - high) * 22))
    return int(35 + (combined_sim - low) / (high - low) * 43)


def _cache_get(topic: str) -> dict[str, dict[str, Any]] | None:
    row = _CACHE.get(topic.strip().lower())
    if not row:
        return None
    exp, data = row
    if time.time() > exp:
        _CACHE.pop(topic.strip().lower(), None)
        return None
    return data


def _cache_set(topic: str, data: dict[str, dict[str, Any]]) -> None:
    _CACHE[topic.strip().lower()] = (time.time() + _CACHE_TTL, data)


def _fetch_corpus_ranks(topic: str) -> list[dict[str, Any]]:
    from web.core.rag_backend import embed_query_cached, rank_persons_by_topic

    query_vec = embed_query_cached(topic)
    return rank_persons_by_topic(
        topic,
        chunk_pool=_CHUNK_POOL,
        min_similarity=_MIN_COMBINED_SIM,
        query_vec=query_vec,
    )


def score_persons_hybrid(
    topic: str,
    persons: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    topic = (topic or "").strip()
    if not topic:
        return {}

    cached = _cache_get(topic)
    if cached is not None:
        return cached

    corpus_map: dict[str, dict[str, Any]] = {}
    try:
        for row in _fetch_corpus_ranks(topic):
            slug = str(row.get("slug") or "")
            if slug:
                corpus_map[slug] = row
    except Exception as exc:
        logger.warning("corpus topic ranking failed: %s", exc)

    sw = _SEMANTIC_WEIGHT
    kw = _KEYWORD_WEIGHT
    if not corpus_map:
        sw, kw = 0.0, 1.0

    merged: dict[str, dict[str, Any]] = {}
    for p in persons:
        slug = str(p.get("slug") or "")
        if not slug:
            continue
        kw_score = score_person_topic_fit(topic, p)
        corp = corpus_map.get(slug)
        if corp:
            sem_score = _sim_to_score(float(corp.get("combined_similarity") or 0))
            final = int(round(sw * sem_score + kw * kw_score))
            reason = (
                f"資料庫語意匹配 {corp.get('best_similarity', 0):.2f}"
                f"（{corp.get('hit_chunks', 0)} 段）"
            )
            source = "hybrid"
        else:
            final = kw_score
            reason = "無向量段落，依關鍵字評估"
            source = "keyword"

        final = max(0, min(100, final))
        tier = fit_tier(final)
        merged[slug] = {
            "topic_fit_score": final,
            "fit_tier": tier,
            "fit_tier_label": fit_tier_label(tier),
            "topic_fit_label": fit_tier_label(tier),
            "debate_rounds": debate_rounds_from_fit(final),
            "fit_reason": reason,
            "fit_source": source,
            "semantic_similarity": corp.get("combined_similarity") if corp else None,
            "keyword_score": kw_score,
        }

    _cache_set(topic, merged)
    return merged


def apply_hybrid_fit(
    topic: str, person: dict[str, Any], scores: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    slug = str(person.get("slug") or "")
    fit = scores.get(slug)
    if not fit:
        row = enrich_person_with_fit(topic, person)
        row["fit_source"] = "keyword"
        return row
    return {**person, **fit}


def rank_persons_for_topic_semantic(
    topic: str,
    persons: list[dict[str, Any]],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    scores = score_persons_hybrid(topic, persons)
    enriched = [apply_hybrid_fit(topic, p, scores) for p in persons]
    enriched.sort(
        key=lambda x: (
            TIER_ORDER.get(x.get("fit_tier") or "low", 9),
            -int(x.get("topic_fit_score") or 0),
            -(float(x.get("semantic_similarity") or 0)),
            x.get("name_zh") or x.get("slug") or "",
        )
    )
    return enriched[: max(1, limit)]


def build_member_fit_plan_semantic(
    topic: str,
    slugs: list[str],
    persons_by_slug: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    persons = [persons_by_slug.get(s) or {"slug": s, "name_zh": s} for s in slugs]
    scores = score_persons_hybrid(topic, persons)
    rows: list[dict[str, Any]] = []
    for slug in slugs:
        base = persons_by_slug.get(slug) or {"slug": slug, "name_zh": slug}
        row = apply_hybrid_fit(topic, base, scores)
        row["person_slug"] = slug
        rows.append(row)
    rows.sort(
        key=lambda x: (-int(x.get("topic_fit_score") or 0), x.get("name_zh") or "")
    )
    for i, row in enumerate(rows):
        row["sort_order"] = i
    return rows
