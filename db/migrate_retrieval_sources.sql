-- RAG 引用存入 chat_messages（與 ensure_chat_schema 一致，可手動執行）

ALTER TABLE chat_messages
    ADD COLUMN IF NOT EXISTS retrieval_sources JSONB DEFAULT '[]'::jsonb;
