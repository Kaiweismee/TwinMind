-- 聊天室加入碼與密碼、訪客
ALTER TABLE chat_sessions
ADD COLUMN IF NOT EXISTS join_code VARCHAR(12);

ALTER TABLE chat_sessions
ADD COLUMN IF NOT EXISTS password_hash TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_sessions_join_code
ON chat_sessions (join_code) WHERE join_code IS NOT NULL;

CREATE TABLE IF NOT EXISTS chat_session_guests (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL
        REFERENCES chat_sessions(id) ON DELETE CASCADE,
    display_name TEXT NOT NULL,
    access_token TEXT NOT NULL UNIQUE,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_session_guests_session
ON chat_session_guests(session_id);

ALTER TABLE chat_messages
ADD COLUMN IF NOT EXISTS guest_id INTEGER
REFERENCES chat_session_guests(id) ON DELETE SET NULL;
