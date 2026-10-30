"""人物 API：人物清單與主題推薦。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from web.repositories import chat_store
from web.services.recommendations import _rank_recommendations_openai


router = APIRouter()


@router.get("/api/persons")
def list_persons():
    from data.person_profiles import PERSON_CATEGORIES

    return {
        "persons": chat_store.list_persons_feed(),
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
    if fast:
        from web.recommendations.topic_fit import rank_persons_for_topic

        ranked = rank_persons_for_topic(topic, persons, limit=limit)
        return {"recommendations": ranked, "topic": topic, "mode": "hybrid"}
    ranked = _rank_recommendations_openai(topic, persons, limit=limit)
    return {"recommendations": ranked, "topic": topic, "mode": "openai"}
