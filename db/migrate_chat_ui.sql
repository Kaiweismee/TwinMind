-- 一對一聊天室 UI：執行一次（pgAdmin 或 psql）
-- 為 chat_sessions 綁定名人；放寬 chat_messages.role 限制

ALTER TABLE chat_sessions
    ADD COLUMN IF NOT EXISTS person_slug TEXT;

ALTER TABLE chat_messages
    DROP CONSTRAINT IF EXISTS chat_messages_role_check;

-- role: user（使用者）, assistant（名人 AI）, moderator, system, 或舊版 musk/jensen

CREATE INDEX IF NOT EXISTS idx_chat_sessions_person_slug ON chat_sessions(person_slug);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_created_at ON chat_sessions(created_at DESC);
