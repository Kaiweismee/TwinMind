-- 無 pgvector 時的備援：用 JSONB 存向量（畢專規模夠用）
BEGIN;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding_json JSONB;
COMMIT;
