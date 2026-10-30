"""RAG 查詢 API：檢索人物資料並回傳來源。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from web.core.dependencies import _resolve_top_k
from web.core.rag_backend import format_context
from web.core.rag_backend import search_chunks
from web.schemas.requests import QueryRequest


router = APIRouter()


@router.post("/api/query")
def api_query(body: QueryRequest):
    question = body.question.strip()
    person = body.person.strip()
    source_types = (
        [t.strip() for t in body.types.split(",") if t.strip()]
        if body.types.strip()
        else None
    )
    if not question or not person:
        raise HTTPException(status_code=400, detail="請提供 question 與 person")
    try:
        results = search_chunks(
            question,
            person_slug=person,
            top_k=_resolve_top_k(body.top_k),
            source_types=source_types,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {
        "question": question,
        "person": person,
        "results": [
            {
                "chunk_id": r["chunk_id"],
                "similarity": round(float(r["similarity"]), 4),
                "source_type": r["source_type"],
                "title": r["title"],
                "source_url": r["source_url"],
                "content": r["content"],
            }
            for r in results
        ],
        "context": format_context(results),
    }
