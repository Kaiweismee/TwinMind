-- 多人討論室：一位使用者 + 多位名人

CREATE TABLE IF NOT EXISTS chat_session_members (
    session_id   INTEGER NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    person_slug  TEXT NOT NULL,
    sort_order   SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, person_slug)
);

CREATE INDEX IF NOT EXISTS idx_chat_session_members_session
    ON chat_session_members(session_id);

-- 舊版單人聊天室：把 person_slug 搬進 members
INSERT INTO chat_session_members (session_id, person_slug, sort_order)
SELECT s.id, s.person_slug, 0
FROM chat_sessions s
WHERE s.person_slug IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM chat_session_members m
      WHERE m.session_id = s.id AND m.person_slug = s.person_slug
  );
