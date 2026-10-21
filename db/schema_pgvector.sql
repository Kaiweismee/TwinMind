-- pgvector：RAG 向量欄位
-- 先安裝：brew install pgvector
-- 執行：psql digital_twin -f db/schema_pgvector.sql
-- 或使用：./venv/bin/python db/setup_pgvector.py

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;

-- 與 paraphrase-multilingual-MiniLM-L12-v2 一致（384 維）
-- 若用 OpenAI text-embedding-3-small，請改為 vector(1536) 並調整 rag/config.py
ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS embedding vector(384);

COMMIT;

-- 索引請在 embed_chunks.py 跑完後建立（需有一定筆數）
