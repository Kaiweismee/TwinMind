CREATE TABLE IF NOT EXISTS chat_join_notifications (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL
        REFERENCES chat_sessions(id) ON DELETE CASCADE,
    guest_name TEXT NOT NULL,
    guest_id INTEGER
        REFERENCES chat_session_guests(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    read_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_join_notifications_session
ON chat_join_notifications(session_id, created_at DESC);
