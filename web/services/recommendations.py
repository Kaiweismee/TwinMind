"""名人推薦流程：執行推薦、處理逾時與錯誤。"""

from __future__ import annotations

from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Any

from fastapi import HTTPException

from web.core.runtime import _RECOMMEND_POOL, _log
from web.core.settings import RECOMMEND_TIMEOUT_SEC


def _rank_recommendations_openai(
    topic: str,
    persons: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    from web.recommendations.topic_fit_llm import openai_configured, rank_persons_for_topic_llm

    if not openai_configured():
        raise HTTPException(
            status_code=503,
            detail="請在 .env 設定 OPENAI_API_KEY 以使用 AI 推薦名人",
        )

    fut = _RECOMMEND_POOL.submit(
        rank_persons_for_topic_llm, topic, persons, limit=limit
    )
    try:
        return fut.result(timeout=RECOMMEND_TIMEOUT_SEC)
    except FuturesTimeout as exc:
        _log.warning(
            "OpenAI topic recommend timed out after %.1fs",
            RECOMMEND_TIMEOUT_SEC,
        )
        raise HTTPException(
            status_code=504,
            detail="AI 推薦分析逾時，請稍後再試",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        _log.warning("OpenAI topic recommend failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"AI 推薦失敗：{exc}",
        ) from exc
