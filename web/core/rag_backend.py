"""網頁連接既有 rag/ 程式的單一入口。

rag/ 的命令列工具仍使用 config、search 等頂層匯入。
只在此加入 rag 路徑並匯出共用功能；web 內部一律使用完整套件路徑。
此模組只載入程式，不建立資料庫連線或執行 embedding。
"""
import sys

from web.core.settings import ROOT

_rag_path = str(ROOT / "rag")
if _rag_path not in sys.path:
    sys.path.insert(0, _rag_path)

from config import DB_CONFIG, DEFAULT_TOP_K  # noqa: E402,F401
from db import connect, connect_dict  # noqa: E402,F401
from embedder import embed_texts  # noqa: E402,F401
from search import (  # noqa: E402,F401
    batch_search_chunks,
    corpus_similarity_available,
    embed_query_cached,
    format_context,
    rank_persons_by_topic,
    search_chunks,
)
from store import MODE_JSON, MODE_PGVECTOR, detect_storage_mode  # noqa: E402,F401
