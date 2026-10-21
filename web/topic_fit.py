"""
依討論主題評估名人契合度，用於推薦參與者與調整發言順序／輪數。

後端模式（.env TOPIC_FIT_BACKEND）：
- hybrid（推薦）：主題向量 × 全庫 chunks 語意排序 + 關鍵字加權
- semantic：僅語意（爬蟲向量庫）
- keyword：手寫關鍵字規則
- llm：hybrid 前 20 名 → OpenAI 重排（最準但較慢、耗 API）
- auto：有向量庫用 hybrid；設 TOPIC_FIT_LLM_RERANK=1 且有 Key 則 llm
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

from data.person_profiles import PERSON_PROFILES, category_for_slug
from data.person_topic_keywords import DOMAIN_TOPIC_KEYWORDS, PERSON_TOPIC_KEYWORDS

_CJK_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
_WORD_RE = re.compile(r"[a-zA-Z0-9]{2,}")


def _topic_terms(topic: str) -> set[str]:
    t = (topic or "").strip().lower()
    if not t:
        return set()
    terms: set[str] = set()
    terms.update(_CJK_RE.findall(t))
    terms.update(w.lower() for w in _WORD_RE.findall(t))
    for frag in re.split(r"[\s,，、？?！!；;：:]+", t):
        frag = frag.strip()
        if len(frag) >= 2:
            terms.add(frag)
    return terms


def _topic_contains_keyword(topic_l: str, kw: str) -> bool:
    k = (kw or "").strip().lower()
    if len(k) < 2:
        return False
    return k in topic_l


def _count_keyword_hits(topic_l: str, keywords: list[str]) -> int:
    seen: set[str] = set()
    hits = 0
    for kw in keywords:
        k = (kw or "").strip().lower()
        if len(k) < 2 or k in seen:
            continue
        seen.add(k)
        if _topic_contains_keyword(topic_l, k):
            hits += 1
    return hits


def debate_rounds_from_fit(score: int) -> int:
    """契合度 → 辯論階段發言輪數（開場各 1 次；高契合 4 輪、中契合 3 輪）。"""
    if score >= 75:
        return 4
    if score >= 55:
        return 3
    if score >= 40:
        return 2
    return 1


TIER_ORDER = {"high": 0, "mid": 1, "low": 2}


def fit_tier(score: int) -> str:
    """高／中／低 三級契合。"""
    if score >= 78:
        return "high"
    if score >= 52:
        return "mid"
    return "low"


def fit_tier_label(tier: str) -> str:
    return {"high": "高", "mid": "中", "low": "低"}.get(tier, "低")


def fit_label(score: int) -> str:
    return fit_tier_label(fit_tier(score))


def score_person_topic_fit(topic: str, person: dict[str, Any]) -> int:
    """0–100：名人專屬關鍵字 + 領域關鍵字 + bio 詞彙重疊。"""
    topic = (topic or "").strip()
    if not topic:
        return 50

    slug = str(person.get("slug") or "")
    bio = (person.get("bio") or "").lower()
    name = f"{person.get('name_zh') or ''} {person.get('name_en') or ''}".lower()
    prof = PERSON_PROFILES.get(slug)
    if prof:
        bio = f"{bio} {prof.get('bio', '')}".lower()

    cat = (person.get("category") or "") or category_for_slug(slug)
    terms = _topic_terms(topic)
    topic_l = topic.lower()

    score = 32.0

    # 名人專屬關鍵字（權重最高）
    person_kws = PERSON_TOPIC_KEYWORDS.get(slug, [])
    # 主題與專屬詞精確／包含匹配（例如「論語」→ 孔子）
    for kw in person_kws:
        k = (kw or "").strip().lower()
        if len(k) < 2:
            continue
        if topic_l == k:
            score += 50.0
            break
        if len(topic_l) >= 2 and (k in topic_l or topic_l in k):
            score += 22.0
            break
    person_hits = _count_keyword_hits(topic_l, person_kws)
    score += min(28.0, max(0, person_hits - 1) * 4.0)

    # 領域通用關鍵字
    domain_kws = DOMAIN_TOPIC_KEYWORDS.get(cat, [])
    domain_hits = _count_keyword_hits(topic_l, domain_kws)
    score += min(22.0, domain_hits * 3.0)

    # 主題詞與 bio／姓名重疊
    for term in terms:
        if len(term) < 2:
            continue
        if term in bio or term in name:
            score += 8.0

    # 主題明顯屬某領域且名人屬該分類
    for domain, keywords in DOMAIN_TOPIC_KEYWORDS.items():
        if not any(_topic_contains_keyword(topic_l, kw) for kw in keywords):
            continue
        if cat == domain or category_for_slug(slug) == domain:
            score += 12.0
            break

    return int(max(0, min(100, round(score))))


def enrich_person_with_fit(topic: str, person: dict[str, Any]) -> dict[str, Any]:
    score = score_person_topic_fit(topic, person)
    tier = fit_tier(score)
    return {
        **person,
        "topic_fit_score": score,
        "fit_tier": tier,
        "fit_tier_label": fit_tier_label(tier),
        "topic_fit_label": fit_tier_label(tier),
        "debate_rounds": debate_rounds_from_fit(score),
    }


def _topic_fit_backend() -> str:
    mode = (os.getenv("TOPIC_FIT_BACKEND") or "auto").strip().lower()
    if mode == "auto":
        try:
            from topic_fit_semantic import corpus_ranking_available
            from topic_fit_llm import openai_configured

            if (
                os.getenv("TOPIC_FIT_LLM_RERANK", "").strip() in ("1", "true", "yes")
                and openai_configured()
                and corpus_ranking_available()
            ):
                return "llm"
            if corpus_ranking_available():
                return "hybrid"
        except Exception:
            pass
        return "keyword"
    if mode in ("llm", "openai", "gpt"):
        return "llm"
    if mode in ("semantic", "rag", "vector"):
        return "semantic"
    if mode in ("hybrid", "blend", "default"):
        return "hybrid"
    return "keyword"


def rank_persons_keyword_only(
    topic: str,
    persons: list[dict[str, Any]],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """僅關鍵字規則排序（供 LLM 模組預篩，避免遞迴）。"""
    enriched = [enrich_person_with_fit(topic, p) for p in persons]
    enriched.sort(
        key=lambda x: (
            TIER_ORDER.get(x.get("fit_tier") or "low", 9),
            -x["topic_fit_score"],
            x.get("name_zh") or x.get("slug") or "",
        )
    )
    return enriched[: max(1, limit)]


def rank_persons_for_topic(
    topic: str,
    persons: list[dict[str, Any]],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    backend = _topic_fit_backend()
    if backend == "llm":
        try:
            from topic_fit_llm import rank_persons_for_topic_llm

            return rank_persons_for_topic_llm(topic, persons, limit=limit)
        except Exception as exc:
            logger.warning("LLM topic fit failed, using hybrid: %s", exc)
            backend = "hybrid"
    if backend in ("hybrid", "semantic"):
        try:
            from topic_fit_semantic import rank_persons_for_topic_semantic

            return rank_persons_for_topic_semantic(topic, persons, limit=limit)
        except Exception as exc:
            logger.warning("Semantic topic fit failed, using keywords: %s", exc)

    return rank_persons_keyword_only(topic, persons, limit=limit)


def build_member_fit_plan(
    topic: str,
    slugs: list[str],
    persons_by_slug: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """建立成員排序與契合度（sort_order 高契合優先）。"""
    backend = _topic_fit_backend()
    if backend == "llm":
        try:
            from topic_fit_llm import build_member_fit_plan_llm

            return build_member_fit_plan_llm(topic, slugs, persons_by_slug)
        except Exception as exc:
            logger.warning("LLM member fit plan failed, using hybrid: %s", exc)
            backend = "hybrid"
    if backend in ("hybrid", "semantic"):
        try:
            from topic_fit_semantic import build_member_fit_plan_semantic

            return build_member_fit_plan_semantic(topic, slugs, persons_by_slug)
        except Exception as exc:
            logger.warning("Semantic member fit failed, using keywords: %s", exc)

    rows: list[dict[str, Any]] = []
    for slug in slugs:
        base = persons_by_slug.get(slug) or {"slug": slug, "name_zh": slug}
        row = enrich_person_with_fit(topic, base)
        row["person_slug"] = slug
        rows.append(row)
    rows.sort(key=lambda x: (-x["topic_fit_score"], x.get("name_zh") or ""))
    for i, row in enumerate(rows):
        row["sort_order"] = i
    return rows
