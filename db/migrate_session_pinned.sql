-- 聊天室釘選
ALTER TABLE chat_sessions
ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_chat_sessions_pinned_updated
ON chat_sessions (pinned DESC, created_at DESC);
