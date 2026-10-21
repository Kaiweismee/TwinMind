"""
啟用 RAG 向量欄位（優先 pgvector，否則 JSONB 備援）

用法：./venv/bin/python db/setup_pgvector.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "rag"))
from store import MODE_JSON, MODE_PGVECTOR, setup_storage


def main() -> None:
    print("設定 RAG 向量儲存 …")
    mode = setup_storage()
    if mode == MODE_PGVECTOR:
        print("✓ 使用 pgvector（chunks.embedding vector(384)）")
        print("  建議：brew install pgvector 後可獲得較快檢索。")
    else:
        print("✓ 使用 JSONB 備援（chunks.embedding_json）")
        print("  不需 pgvector，畢專規模可正常 RAG。")
        print("  之後若安裝 pgvector，可再執行本腳本升級。")


if __name__ == "__main__":
    main()
