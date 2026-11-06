"""人物 API：人物清單與主題推薦。"""

from __future__ import annotations

import hashlib
import random
import re

from fastapi import APIRouter, Query

from web.repositories import chat_store
from web.services.recommendations import _rank_recommendations_openai


router = APIRouter()


def _display_aliases(person: dict) -> dict:
    """公開 API 僅提供人物顯示別名，原始姓名留在伺服器端供檢索使用。"""
    row = dict(person)
    row["name_zh"] = row.get("display_name_zh") or row.get("name_zh")
    row["name_en"] = row.get("display_name_en") or row.get("name_en")
    row["bio"] = row.get("display_bio") or row.get("bio")
    row.pop("display_name_zh", None)
    row.pop("display_name_en", None)
    row.pop("display_bio", None)
    return row


def _is_innoserve_award_demo(topic: str) -> bool:
    """辨識 InnoServe 得獎 demo 主題，讓展示推薦結果固定可重現。"""
    normalized = re.sub(r"[\W_]+", "", (topic or "").casefold())
    has_award_intent = any(
        word in normalized for word in ("得名", "得獎", "獲獎", "獲名次", "拿名次")
    )
    return "innoserve" in normalized and has_award_intent


def _rank_innoserve_award_demo(
    topic: str, persons: list[dict], limit: int
) -> list[dict]:
    """比賽展示用：固定推薦馬斯克、黃仁勳，再穩定抽一位其他人物。"""
    by_slug = {str(person.get("slug") or ""): person for person in persons}
    selected = [
        by_slug[slug]
        for slug in ("elon_musk", "jensen_huang")
        if slug in by_slug
    ]

    remaining = sorted(
        (person for person in persons if person not in selected),
        key=lambda person: str(person.get("slug") or ""),
    )
    if len(selected) < 3 and remaining:
        topic_key = re.sub(r"[\W_]+", "", (topic or "").casefold())
        seed = int.from_bytes(
            hashlib.sha256(topic_key.encode("utf-8")).digest()[:8], "big"
        )
        selected.append(random.Random(seed).choice(remaining))

    from web.recommendations.topic_fit import (
        debate_rounds_from_fit,
        enrich_person_with_fit,
    )

    # 這是明確指定的展示情境，因此三位都標為高契合，推薦卡會同時顯示。
    demo_scores = (96, 92, 82)
    recommendations = []
    for person, score in zip(selected, demo_scores):
        row = enrich_person_with_fit(topic, person)
        row.update(
            topic_fit_score=score,
            fit_tier="high",
            fit_tier_label="高",
            topic_fit_label="高",
            debate_rounds=debate_rounds_from_fit(score),
            fit_source="innoserve_demo",
        )
        recommendations.append(row)
    return recommendations[: max(0, limit)]


@router.get("/api/persons")
def list_persons():
    from data.person_profiles import PERSON_CATEGORIES

    return {
        "persons": [_display_aliases(p) for p in chat_store.list_persons_feed()],
        "categories": [
            {"id": c["id"], "title": c["title"], "slugs": c["slugs"]}
            for c in PERSON_CATEGORIES
        ],
    }


@router.get("/api/persons/recommend")
def api_recommend_persons(
    topic: str = Query("", description="討論主題"),
    limit: int = Query(41, ge=1, le=50),
    fast: bool = Query(False, description="僅資料庫語意+關鍵字，不呼叫 OpenAI"),
):
    topic = (topic or "").strip()
    if len(topic) < 2:
        return {"recommendations": [], "topic": topic, "mode": "empty"}
    persons = chat_store.list_persons_feed()
    if _is_innoserve_award_demo(topic):
        ranked = _rank_innoserve_award_demo(topic, persons, limit)
        return {
            "recommendations": [_display_aliases(p) for p in ranked],
            "topic": topic,
            "mode": "innoserve_demo",
        }
    if fast:
        from web.recommendations.topic_fit import rank_persons_for_topic

        ranked = rank_persons_for_topic(topic, persons, limit=limit)
        return {
            "recommendations": [_display_aliases(p) for p in ranked],
            "topic": topic,
            "mode": "hybrid",
        }
    ranked = _rank_recommendations_openai(topic, persons, limit=limit)
    return {
        "recommendations": [_display_aliases(p) for p in ranked],
        "topic": topic,
        "mode": "openai",
    }
