"""RAG 設定：資料庫、embedding 模型"""

import os

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "digital_twin",
    "user": "kaiwei",
}

# 本機免 API key，支援中英文（畢專預設）
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "paraphrase-multilingual-MiniLM-L12-v2",
)
EMBEDDING_DIM = 384

# 若有 OPENAI_API_KEY，可設 EMBEDDING_BACKEND=openai 改用 text-embedding-3-small（1536 維）
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "local")
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
OPENAI_EMBEDDING_DIM = 1536

BATCH_SIZE = 32

# RAG 檢索筆數：0 = 不固定 5 筆，改依相似度門檻取回（見 search.py）
# 設為正整數則固定取前 N 段；RAG_MAX_CHUNKS 為安全上限
def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    return int(raw)


DEFAULT_TOP_K = _int_env("RAG_TOP_K", 8)
RAG_MIN_SIMILARITY = float(os.getenv("RAG_MIN_SIMILARITY", "0.2"))
RAG_MAX_CHUNKS = _int_env("RAG_MAX_CHUNKS", 200)
