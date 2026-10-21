"""
RAG 測試：在終端機問問題，看檢索結果

用法：
  ./venv/bin/python rag/query.py "黃仁勳怎麼看 AI" --person jensen_huang
  ./venv/bin/python rag/query.py "Tesla future" --person elon_musk --types speech,interview
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import DEFAULT_TOP_K
from search import format_context, search_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 語意搜尋測試")
    parser.add_argument("question", help="你的問題")
    parser.add_argument(
        "--person",
        required=True,
        help="名人 slug（persons 表，例如 elon_musk、bill_gates）",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help="回傳幾段；0=依相似度門檻取回全部相關段落",
    )
    parser.add_argument(
        "--types",
        default="",
        help="只搜這些來源，逗號分隔，例如 speech,interview,news",
    )
    args = parser.parse_args()

    source_types = [t.strip() for t in args.types.split(",") if t.strip()] or None

    print(f"問題：{args.question}")
    print(f"人物：{args.person}")
    if source_types:
        print(f"來源：{source_types}")
    print()

    results = search_chunks(
        args.question,
        person_slug=args.person,
        top_k=args.top_k,
        source_types=source_types,
    )

    if not results:
        print("沒有找到結果。請先執行：")
        print("  ./venv/bin/python db/setup_pgvector.py")
        print("  ./venv/bin/python rag/embed_chunks.py")
        return

    print("=== 檢索結果 ===\n")
    for i, r in enumerate(results, 1):
        print(f"--- [{i}] 相似度 {r['similarity']:.3f} | {r['source_type']} ---")
        print(f"標題：{r['title']}")
        print(f"URL：{r['source_url']}")
        print(f"內容：{r['content'][:400]}{'…' if len(r['content']) > 400 else ''}\n")

    print("=== 組合 Context（給 LLM）===\n")
    print(format_context(results))


if __name__ == "__main__":
    main()
