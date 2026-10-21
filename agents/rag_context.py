"""RAG 檢索（供 CrewAI 使用）"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent / "rag"))

from config import DEFAULT_TOP_K  # noqa: E402
from search import format_context, search_chunks  # noqa: E402


def retrieve_for_person(
    person_slug: str,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    source_types: list[str] | None = None,
) -> tuple[str, list[int], list[dict[str, Any]]]:
    """
    回傳：(context 字串, chunk_id 列表, 原始检索结果)
    """
    results = search_chunks(
        query,
        person_slug=person_slug,
        top_k=top_k,
        source_types=source_types,
    )
    chunk_ids = [int(r["chunk_id"]) for r in results]
    context = format_context(results)
    if not context.strip():
        context = "（知識庫未檢索到相關資料，請謹慎發言並註明是推測。）"
    return context, chunk_ids, results
