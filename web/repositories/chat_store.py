"""聊天室與歷史紀錄（PostgreSQL）— 支援多人討論"""

from __future__ import annotations

import os
from typing import Any

import psycopg2
from psycopg2.extras import Json, RealDictCursor

from web.core.rag_backend import DB_CONFIG
from web.core.session_auth import hash_password, new_join_code, verify_password

USER_DISPLAY_NAME = os.getenv("APP_USER_NAME", "kaiweisme")
USER_DISPLAY_BIO = os.getenv("APP_USER_BIO", "數位分身畢專 · 本機開發")
USER_AVATAR_URL = os.getenv("APP_USER_AVATAR", "/static/icon.png")

# 你的數位分身示範資料（尚未建 RAG 知識庫時使用）
USER_TWIN_MOCK_CONTEXT = os.getenv(
    "APP_USER_TWIN_BIO",
    """
你是使用者的數位分身「{name}」，台灣大學資訊相關背景，正在進行數位分身畢業專題。
你關心：AI 倫理、創業與學習效率、科技對社會的影響。
說話風格：務實、願意承認不確定、會用生活例子，繁體中文，不要太官腔。
目前知識庫尚在建置，可根據以上設定發言，勿捏造具體新聞日期或統計數字。
""".strip(),
)
MAX_GROUP_SIZE = int(os.getenv("CHAT_MAX_PARTICIPANTS", "6"))


def _conn():
    return psycopg2.connect(**DB_CONFIG)


def ensure_chat_schema() -> None:
    """啟動時套用輕量 migration（可重複執行）"""
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS person_slug TEXT;"
            )
            cur.execute(
                """
                ALTER TABLE chat_messages
                DROP CONSTRAINT IF EXISTS chat_messages_role_check;
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_session_members (
                    session_id   INTEGER NOT NULL
                        REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    person_slug  TEXT NOT NULL,
                    sort_order   SMALLINT NOT NULL DEFAULT 0,
                    PRIMARY KEY (session_id, person_slug)
                );
                """
            )
            cur.execute(
                """
                ALTER TABLE chat_session_members
                ADD COLUMN IF NOT EXISTS topic_fit_score SMALLINT;
                """
            )
            cur.execute(
                """
                ALTER TABLE chat_session_members
                ADD COLUMN IF NOT EXISTS debate_rounds SMALLINT NOT NULL DEFAULT 1;
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_session_members_session
                ON chat_session_members(session_id);
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_session_users (
                    session_id INTEGER NOT NULL
                        REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL
                        REFERENCES users(id) ON DELETE CASCADE,
                    display_name TEXT,
                    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (session_id, user_id)
                );
                """
            )
            cur.execute(
                """
                ALTER TABLE chat_session_users
                ADD COLUMN IF NOT EXISTS display_name TEXT;
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_session_users_user
                ON chat_session_users(user_id, joined_at DESC);
                """
            )
            cur.execute(
                """
                INSERT INTO chat_session_users (session_id, user_id)
                SELECT s.id, s.owner_user_id
                FROM chat_sessions s
                WHERE s.owner_user_id IS NOT NULL
                ON CONFLICT (session_id, user_id) DO NOTHING;
                """
            )
            cur.execute(
                """
                INSERT INTO chat_session_members (session_id, person_slug, sort_order)
                SELECT s.id, s.person_slug, 0
                FROM chat_sessions s
                WHERE s.person_slug IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM chat_session_members m
                      WHERE m.session_id = s.id AND m.person_slug = s.person_slug
                  );
                """
            )
            cur.execute(
                "ALTER TABLE persons ADD COLUMN IF NOT EXISTS avatar_url TEXT;"
            )
            cur.execute(
                "ALTER TABLE persons ADD COLUMN IF NOT EXISTS avatar_source TEXT;"
            )
            cur.execute(
                """
                ALTER TABLE persons
                ADD COLUMN IF NOT EXISTS links JSONB NOT NULL DEFAULT '{}'::jsonb;
                """
            )
            cur.execute(
                "ALTER TABLE persons ADD COLUMN IF NOT EXISTS category TEXT;"
            )
            cur.execute(
                "ALTER TABLE persons ADD COLUMN IF NOT EXISTS display_name_zh TEXT;"
            )
            cur.execute(
                "ALTER TABLE persons ADD COLUMN IF NOT EXISTS display_name_en TEXT;"
            )
            cur.execute(
                "ALTER TABLE persons ADD COLUMN IF NOT EXISTS display_bio TEXT;"
            )
            cur.execute(
                """
                ALTER TABLE chat_messages
                ADD COLUMN IF NOT EXISTS retrieval_sources JSONB
                DEFAULT '[]'::jsonb;
                """
            )
            cur.execute(
                """
                ALTER TABLE chat_sessions
                ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT FALSE;
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_pinned_updated
                ON chat_sessions (pinned DESC, created_at DESC);
                """
            )
            cur.execute(
                """
                ALTER TABLE chat_sessions
                ADD COLUMN IF NOT EXISTS join_code VARCHAR(12);
                """
            )
            cur.execute(
                """
                ALTER TABLE chat_sessions
                ADD COLUMN IF NOT EXISTS password_hash TEXT;
                """
            )
            cur.execute(
                """
                ALTER TABLE chat_sessions
                ADD COLUMN IF NOT EXISTS allow_guest_join BOOLEAN NOT NULL DEFAULT TRUE;
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_sessions_join_code
                ON chat_sessions (join_code) WHERE join_code IS NOT NULL;
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_session_guests (
                    id SERIAL PRIMARY KEY,
                    session_id INTEGER NOT NULL
                        REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    display_name TEXT NOT NULL,
                    access_token TEXT NOT NULL UNIQUE,
                    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_session_guests_session
                ON chat_session_guests(session_id);
                """
            )
            cur.execute(
                """
                ALTER TABLE chat_messages
                ADD COLUMN IF NOT EXISTS guest_id INTEGER
                REFERENCES chat_session_guests(id) ON DELETE SET NULL;
                """
            )
            cur.execute(
                """
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
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_join_notifications_session
                ON chat_join_notifications(session_id, created_at DESC);
                """
            )
            cur.execute(
                """
                ALTER TABLE chat_sessions
                ADD COLUMN IF NOT EXISTS context_brief TEXT;
                """
            )
            cur.execute(
                """
                ALTER TABLE chat_sessions
                ADD COLUMN IF NOT EXISTS context_files JSONB NOT NULL DEFAULT '[]'::jsonb;
                """
            )
            cur.execute(
                """
                UPDATE chat_sessions
                SET join_code = UPPER(SUBSTRING(MD5(id::text || topic) FROM 1 FOR 6))
                WHERE join_code IS NULL;
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_session_insights (
                    session_id INTEGER PRIMARY KEY
                        REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    llm_message_count INTEGER NOT NULL DEFAULT 0,
                    insights JSONB NOT NULL DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        conn.commit()
        from web.knowledge.person_profile_seed import seed_person_profiles

        seed_person_profiles()
    finally:
        conn.close()


def get_profile() -> dict[str, str]:
    return {
        "display_name": USER_DISPLAY_NAME,
        "username": USER_DISPLAY_NAME,
        "bio": USER_DISPLAY_BIO,
        "avatar_url": USER_AVATAR_URL,
        "avatar_letter": USER_DISPLAY_NAME[:1].upper() or "K",
        "twin_context": USER_TWIN_MOCK_CONTEXT.format(name=USER_DISPLAY_NAME),
    }


def list_persons_feed() -> list[dict[str, Any]]:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT p.slug, p.name_zh, p.name_en,
                       p.display_name_zh, p.display_name_en, p.display_bio,
                       p.bio,
                       p.avatar_url, p.avatar_source, p.links, p.category,
                       COUNT(DISTINCT d.id) AS doc_count,
                       COUNT(DISTINCT c.id) AS chunk_count
                FROM persons p
                LEFT JOIN documents d ON d.person_id = p.id
                LEFT JOIN chunks c ON c.document_id = d.id
                WHERE p.slug !~ '^user_'
                GROUP BY p.id, p.slug, p.name_zh, p.name_en,
                         p.display_name_zh, p.display_name_en, p.display_bio, p.bio,
                         p.avatar_url, p.avatar_source, p.links, p.category
                ORDER BY p.name_zh;
                """
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def _fetch_members(cur, session_id: int) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT m.person_slug, m.sort_order, m.topic_fit_score, m.debate_rounds,
               COALESCE(p.display_name_zh, p.name_zh) AS name_zh,
               COALESCE(p.display_name_en, p.name_en) AS name_en,
               p.avatar_url, COALESCE(p.display_bio, p.bio) AS bio, p.category
        FROM chat_session_members m
        JOIN persons p ON p.slug = m.person_slug
        WHERE m.session_id = %s
        ORDER BY m.sort_order, p.name_zh;
        """,
        (session_id,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    try:
        from web.recommendations.topic_fit import debate_rounds_from_fit

        for r in rows:
            sc = r.get("topic_fit_score")
            if sc is not None:
                r["debate_rounds"] = debate_rounds_from_fit(int(sc))
    except Exception:
        pass
    return rows


def _unique_join_code(cur) -> str:
    for _ in range(20):
        code = new_join_code()
        cur.execute(
            "SELECT 1 FROM chat_sessions WHERE join_code = %s;",
            (code,),
        )
        if not cur.fetchone():
            return code
    return new_join_code(8)


def create_session(
    person_slugs: list[str],
    title: str | None = None,
    room_password: str | None = None,
    owner_user_id: int | None = None,
    *,
    allow_guest_join: bool = True,
) -> dict[str, Any]:
    slugs = []
    seen: set[str] = set()
    for raw in person_slugs:
        s = raw.strip()
        if s and s not in seen:
            if s.startswith("user_"):
                raise ValueError(f"無法將私人知識庫 slug 加入討論室：{s}")
            seen.add(s)
            slugs.append(s)

    if not slugs:
        raise ValueError("請至少選擇一位名人")
    if not title or not str(title).strip():
        raise ValueError("請輸入討論主題")
    if len(slugs) > MAX_GROUP_SIZE:
        raise ValueError(f"最多 {MAX_GROUP_SIZE} 位名人")

    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            names: list[str] = []
            for slug in slugs:
                cur.execute(
                    """
                    SELECT COALESCE(display_name_zh, name_zh) AS name_zh
                    FROM persons WHERE slug = %s;
                    """,
                    (slug,),
                )
                person = cur.fetchone()
                if not person:
                    raise ValueError(f"找不到名人：{slug}")
                names.append(person["name_zh"])

            topic = str(title).strip()
            join_code = _unique_join_code(cur)
            allow_join = bool(allow_guest_join)
            pwd = (room_password or "").strip() if allow_join else ""
            password_hash = hash_password(pwd) if pwd else None

            cur.execute(
                """
                INSERT INTO chat_sessions (
                    topic, person_slug, join_code, password_hash, owner_user_id,
                    allow_guest_join
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, topic, person_slug, join_code, created_at, allow_guest_join;
                """,
                (topic, slugs[0], join_code, password_hash, owner_user_id, allow_join),
            )
            row = dict(cur.fetchone())
            row["has_password"] = bool(password_hash)
            row["allow_guest_join"] = bool(row.get("allow_guest_join", allow_join))
            session_id = row["id"]

            from web.recommendations.topic_fit import build_member_fit_plan

            feed = list_persons_feed()
            by_slug = {p["slug"]: p for p in feed}
            fit_plan = build_member_fit_plan(topic, slugs, by_slug)

            for m in fit_plan:
                cur.execute(
                    """
                    INSERT INTO chat_session_members (
                        session_id, person_slug, sort_order,
                        topic_fit_score, debate_rounds
                    )
                    VALUES (%s, %s, %s, %s, %s);
                    """,
                    (
                        session_id,
                        m["person_slug"],
                        m["sort_order"],
                        m["topic_fit_score"],
                        m["debate_rounds"],
                    ),
                )

            if owner_user_id is not None:
                cur.execute(
                    """
                    INSERT INTO chat_session_users (session_id, user_id)
                    VALUES (%s, %s)
                    ON CONFLICT (session_id, user_id) DO NOTHING;
                    """,
                    (session_id, owner_user_id),
                )

            row["members"] = _fetch_members(cur, session_id)
        conn.commit()
        return row
    finally:
        conn.close()


def _enrich_session_rows(cur, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for r in rows:
        r["has_password"] = bool(r.get("password_hash"))
        r.pop("password_hash", None)
        r["members"] = _fetch_members(cur, r["id"])
        if not r.get("members_label") and r["members"]:
            r["members_label"] = "、".join(m["name_zh"] for m in r["members"])
        if not r.get("members_label") and r.get("person_slug"):
            cur.execute(
                "SELECT COALESCE(display_name_zh, name_zh) AS name_zh, avatar_url FROM persons WHERE slug = %s;",
                (r["person_slug"],),
            )
            p = cur.fetchone()
            if p:
                r["members_label"] = p["name_zh"]
                if not r["members"]:
                    r["members"] = [{
                        "person_slug": r["person_slug"],
                        "name_zh": p["name_zh"],
                        "avatar_url": p.get("avatar_url"),
                        "sort_order": 0,
                    }]
        r["person_name_zh"] = r.get("members_label")
        cur.execute(
            """
            SELECT COUNT(*)::int AS n FROM chat_session_guests g
            WHERE g.session_id = %s;
            """,
            (r["id"],),
        )
        r["guest_count"] = cur.fetchone()["n"]
    return rows


def list_sessions(
    limit: int = 50,
    session_ids: list[int] | None = None,
    public_only: bool = False,
    owner_user_id: int | None = None,
) -> list[dict[str, Any]]:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if session_ids:
                cur.execute(
                    """
                    SELECT s.id, s.topic, s.person_slug, s.created_at, s.ended_at,
                           s.join_code,
                           COALESCE(s.pinned, FALSE) AS pinned,
                           (s.password_hash IS NOT NULL) AS has_password,
                           (
                               SELECT string_agg(
                                   COALESCE(p.display_name_zh, p.name_zh),
                                   '、' ORDER BY m.sort_order
                               )
                               FROM chat_session_members m
                               JOIN persons p ON p.slug = m.person_slug
                               WHERE m.session_id = s.id
                           ) AS members_label,
                           (
                               SELECT COUNT(*)::int FROM chat_session_members m
                               WHERE m.session_id = s.id
                           ) AS member_count,
                           (
                               SELECT content FROM chat_messages msg
                               WHERE msg.session_id = s.id
                               ORDER BY msg.created_at DESC LIMIT 1
                           ) AS last_message,
                           COALESCE(
                               (SELECT MAX(msg.created_at) FROM chat_messages msg
                                WHERE msg.session_id = s.id),
                               s.created_at
                           ) AS updated_at
                    FROM chat_sessions s
                    WHERE s.id = ANY(%s::int[])
                    ORDER BY COALESCE(s.pinned, FALSE) DESC,
                             updated_at DESC NULLS LAST;
                    """,
                    (session_ids,),
                )
            elif owner_user_id is not None:
                cur.execute(
                    """
                    SELECT s.id, s.topic, s.person_slug, s.created_at, s.ended_at,
                           s.join_code,
                           COALESCE(s.pinned, FALSE) AS pinned,
                           (s.password_hash IS NOT NULL) AS has_password,
                           (
                               SELECT string_agg(
                                   COALESCE(p.display_name_zh, p.name_zh),
                                   '、' ORDER BY m.sort_order
                               )
                               FROM chat_session_members m
                               JOIN persons p ON p.slug = m.person_slug
                               WHERE m.session_id = s.id
                           ) AS members_label,
                           (
                               SELECT COUNT(*)::int FROM chat_session_members m
                               WHERE m.session_id = s.id
                           ) AS member_count,
                           (
                               SELECT content FROM chat_messages msg
                               WHERE msg.session_id = s.id
                               ORDER BY msg.created_at DESC LIMIT 1
                           ) AS last_message,
                           COALESCE(
                               (SELECT MAX(msg.created_at) FROM chat_messages msg
                                WHERE msg.session_id = s.id),
                               s.created_at
                           ) AS updated_at
                    FROM chat_sessions s
                    WHERE s.owner_user_id = %s
                    ORDER BY COALESCE(s.pinned, FALSE) DESC,
                             updated_at DESC NULLS LAST
                    LIMIT %s;
                    """,
                    (owner_user_id, limit),
                )
            elif public_only:
                cur.execute(
                    """
                    SELECT s.id, s.topic, s.person_slug, s.created_at, s.ended_at,
                           s.join_code,
                           COALESCE(s.pinned, FALSE) AS pinned,
                           FALSE AS has_password,
                           (
                               SELECT string_agg(
                                   COALESCE(p.display_name_zh, p.name_zh),
                                   '、' ORDER BY m.sort_order
                               )
                               FROM chat_session_members m
                               JOIN persons p ON p.slug = m.person_slug
                               WHERE m.session_id = s.id
                           ) AS members_label,
                           (
                               SELECT COUNT(*)::int FROM chat_session_members m
                               WHERE m.session_id = s.id
                           ) AS member_count,
                           (
                               SELECT content FROM chat_messages msg
                               WHERE msg.session_id = s.id
                               ORDER BY msg.created_at DESC LIMIT 1
                           ) AS last_message,
                           COALESCE(
                               (SELECT MAX(msg.created_at) FROM chat_messages msg
                                WHERE msg.session_id = s.id),
                               s.created_at
                           ) AS updated_at
                    FROM chat_sessions s
                    WHERE s.password_hash IS NULL
                      AND (
                        EXISTS (SELECT 1 FROM chat_session_members m WHERE m.session_id = s.id)
                        OR s.person_slug IS NOT NULL
                      )
                    ORDER BY COALESCE(s.pinned, FALSE) DESC,
                             updated_at DESC NULLS LAST
                    LIMIT %s;
                    """,
                    (limit,),
                )
            else:
                return []
            rows = [dict(r) for r in cur.fetchall()]
            return _enrich_session_rows(cur, rows)
    finally:
        conn.close()


def list_all_session_ids(limit: int = 200) -> list[int]:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM chat_sessions
                ORDER BY created_at DESC LIMIT %s;
                """,
                (limit,),
            )
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def get_session_by_join_code(join_code: str) -> dict[str, Any] | None:
    code = (join_code or "").strip().upper()
    if not code:
        return None
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT s.id, s.topic, s.join_code,
                       COALESCE(s.allow_guest_join, TRUE) AS allow_guest_join,
                       (s.password_hash IS NOT NULL) AS has_password
                FROM chat_sessions s
                WHERE s.join_code = %s;
                """,
                (code,),
            )
            row = cur.fetchone()
            if not row:
                return None
            session = dict(row)
            session["members"] = _fetch_members(cur, session["id"])
            session["members_label"] = "、".join(
                m["name_zh"] for m in session["members"]
            )
            return session
    finally:
        conn.close()


def join_session_for_user(
    join_code: str,
    user_id: int,
    display_name: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    code = (join_code or "").strip().upper()
    join_name = (display_name or "").strip()
    if not code:
        raise ValueError("請輸入加入碼")
    if user_id <= 0:
        raise ValueError("請先登入")
    if len(join_name) > 40:
        raise ValueError("暱稱過長")

    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if not join_name:
                cur.execute(
                    """
                    SELECT COALESCE(NULLIF(display_name, ''), username) AS display_name
                    FROM users
                    WHERE id = %s;
                    """,
                    (user_id,),
                )
                user_row = cur.fetchone()
                if not user_row:
                    raise ValueError("找不到使用者")
                join_name = (user_row.get("display_name") or "").strip() or "使用者"
            cur.execute(
                """
                SELECT id, topic, join_code, password_hash, allow_guest_join, owner_user_id
                FROM chat_sessions WHERE join_code = %s;
                """,
                (code,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("找不到此加入碼")
            session = dict(row)
            if not session.get("allow_guest_join", True):
                raise ValueError("此討論室不開放加入")
            if session.get("password_hash"):
                if not password or not verify_password(password, session["password_hash"]):
                    raise ValueError("密碼錯誤")
            cur.execute(
                """
                INSERT INTO chat_session_users (session_id, user_id, display_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (session_id, user_id) DO UPDATE
                SET display_name = EXCLUDED.display_name,
                    joined_at = NOW();
                """,
                (session["id"], user_id, join_name),
            )
            if session.get("owner_user_id") != user_id:
                cur.execute(
                    """
                    INSERT INTO chat_join_notifications (session_id, guest_name)
                    VALUES (%s, %s);
                    """,
                    (session["id"], join_name),
                )
            cur.execute(
                """
                SELECT display_name
                FROM chat_session_users
                WHERE session_id = %s AND user_id = %s;
                """,
                (session["id"], user_id),
            )
            joined = cur.fetchone()
        conn.commit()
        full = get_session(session["id"])
        return {
            "session": full,
            "is_owner": session.get("owner_user_id") == user_id,
            "guest_name": (joined or {}).get("display_name") or join_name,
        }
    finally:
        conn.close()


def get_guest_by_token(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT g.id, g.session_id, g.display_name, g.access_token
                FROM chat_session_guests g
                WHERE g.access_token = %s;
                """,
                (token,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def check_session_access(
    session_id: int,
    *,
    is_owner: bool = False,
    guest_token: str | None = None,
    user_id: int | None = None,
) -> tuple[bool, str | None]:
    """回傳 (允許, 錯誤訊息)"""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT password_hash, owner_user_id
                FROM chat_sessions WHERE id = %s;
                """,
                (session_id,),
            )
            row = cur.fetchone()
            if not row:
                return False, "找不到聊天室"
            if user_id is None:
                return False, "請先登入"
            owner_user_id = row.get("owner_user_id")
            if owner_user_id is not None:
                is_owner = user_id == owner_user_id
            if is_owner:
                return True, None
            cur.execute(
                """
                SELECT 1
                FROM chat_session_users
                WHERE session_id = %s AND user_id = %s;
                """,
                (session_id, user_id),
            )
            if cur.fetchone():
                return True, None
            return False, "尚未加入此討論室"
    finally:
        conn.close()


def list_join_notifications(
    session_ids: list[int],
    *,
    unread_only: bool = True,
    limit: int = 30,
    owner_user_id: int | None = None,
) -> list[dict[str, Any]]:
    if not session_ids and owner_user_id is None:
        return []
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            read_filter = "AND n.read_at IS NULL" if unread_only else ""
            if owner_user_id is not None:
                cur.execute(
                    f"""
                    SELECT n.id, n.session_id, n.guest_name, n.created_at,
                           n.read_at IS NOT NULL AS is_read,
                           s.topic AS session_topic
                    FROM chat_join_notifications n
                    JOIN chat_sessions s ON s.id = n.session_id
                    WHERE s.owner_user_id = %s
                    {read_filter}
                    ORDER BY n.created_at DESC
                    LIMIT %s;
                    """,
                    (owner_user_id, limit),
                )
            else:
                cur.execute(
                    f"""
                    SELECT n.id, n.session_id, n.guest_name, n.created_at,
                           n.read_at IS NOT NULL AS is_read,
                           s.topic AS session_topic
                    FROM chat_join_notifications n
                    JOIN chat_sessions s ON s.id = n.session_id
                    WHERE n.session_id = ANY(%s::int[])
                    {read_filter}
                    ORDER BY n.created_at DESC
                    LIMIT %s;
                    """,
                    (session_ids, limit),
                )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def count_unread_notifications(
    session_ids: list[int],
    *,
    owner_user_id: int | None = None,
) -> int:
    if not session_ids and owner_user_id is None:
        return 0
    conn = _conn()
    try:
        with conn.cursor() as cur:
            if owner_user_id is not None:
                cur.execute(
                    """
                    SELECT COUNT(*)::int
                    FROM chat_join_notifications n
                    JOIN chat_sessions s ON s.id = n.session_id
                    WHERE s.owner_user_id = %s AND n.read_at IS NULL;
                    """,
                    (owner_user_id,),
                )
            else:
                cur.execute(
                    """
                    SELECT COUNT(*)::int FROM chat_join_notifications
                    WHERE session_id = ANY(%s::int[]) AND read_at IS NULL;
                    """,
                    (session_ids,),
                )
            return cur.fetchone()[0]
    finally:
        conn.close()


def mark_notifications_read(
    session_ids: list[int] | None = None,
    notification_ids: list[int] | None = None,
    owner_user_id: int | None = None,
) -> int:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            if notification_ids:
                cur.execute(
                    """
                    UPDATE chat_join_notifications
                    SET read_at = NOW()
                    WHERE id = ANY(%s::int[]) AND read_at IS NULL;
                    """,
                    (notification_ids,),
                )
            elif owner_user_id is not None:
                cur.execute(
                    """
                    UPDATE chat_join_notifications n
                    SET read_at = NOW()
                    FROM chat_sessions s
                    WHERE n.session_id = s.id
                      AND s.owner_user_id = %s
                      AND n.read_at IS NULL;
                    """,
                    (owner_user_id,),
                )
            elif session_ids:
                cur.execute(
                    """
                    UPDATE chat_join_notifications
                    SET read_at = NOW()
                    WHERE session_id = ANY(%s::int[]) AND read_at IS NULL;
                    """,
                    (session_ids,),
                )
            else:
                return 0
            updated = cur.rowcount
        conn.commit()
        return updated
    finally:
        conn.close()


def list_session_guests(session_id: int) -> list[dict[str, Any]]:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, display_name, joined_at
                FROM chat_session_guests
                WHERE session_id = %s
                ORDER BY joined_at ASC;
                """,
                (session_id,),
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def set_session_pinned(session_id: int, pinned: bool) -> dict[str, Any] | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                UPDATE chat_sessions
                SET pinned = %s
                WHERE id = %s
                RETURNING id, topic, pinned;
                """,
                (pinned, session_id),
            )
            row = cur.fetchone()
        conn.commit()
        if not row:
            return None
        return dict(row)
    finally:
        conn.close()


def delete_session_for_user(session_id: int) -> bool:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM chat_sessions
                WHERE id = %s;
                """,
                (session_id,),
            )
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted
    finally:
        conn.close()


def update_session_context(
    session_id: int,
    *,
    context_brief: str = "",
    context_files: list[dict[str, Any]] | None = None,
) -> None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE chat_sessions
                SET context_brief = %s,
                    context_files = %s::jsonb
                WHERE id = %s;
                """,
                (
                    (context_brief or "").strip() or None,
                    Json(context_files or []),
                    session_id,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def list_user_session_media_files(
    owner_user_id: int,
    *,
    limit: int = 120,
) -> list[dict[str, Any]]:
    """Collect files uploaded to room context by this user."""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, topic, created_at, COALESCE(context_files, '[]'::jsonb) AS context_files
                FROM chat_sessions
                WHERE owner_user_id = %s
                  AND jsonb_array_length(COALESCE(context_files, '[]'::jsonb)) > 0
                ORDER BY created_at DESC
                LIMIT %s;
                """,
                (owner_user_id, limit),
            )
            rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

    items: list[dict[str, Any]] = []
    for row in rows:
        for raw in row.get("context_files") or []:
            a = dict(raw)
            a.pop("data_url", None)
            items.append(
                {
                    "source": "session_context",
                    "session_id": row.get("id"),
                    "session_topic": row.get("topic") or "",
                    "created_at": row.get("created_at"),
                    "file": a,
                }
            )
    return items


def get_session(session_id: int) -> dict[str, Any] | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT s.id, s.topic, s.person_slug, s.created_at, s.ended_at,
                       s.join_code,
                       COALESCE(s.pinned, FALSE) AS pinned,
                       (s.password_hash IS NOT NULL) AS has_password,
                       s.owner_user_id,
                       s.context_brief,
                       COALESCE(s.context_files, '[]'::jsonb) AS context_files
                FROM chat_sessions s
                WHERE s.id = %s;
                """,
                (session_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            session = dict(row)
            members = _fetch_members(cur, session_id)
            if not members and session.get("person_slug"):
                cur.execute(
                    """
                    SELECT COALESCE(display_name_zh, name_zh) AS name_zh,
                           COALESCE(display_name_en, name_en) AS name_en
                    FROM persons WHERE slug = %s;
                    """,
                    (session["person_slug"],),
                )
                p = cur.fetchone()
                if p:
                    members = [{
                        "person_slug": session["person_slug"],
                        "sort_order": 0,
                        "name_zh": p["name_zh"],
                        "name_en": p["name_en"],
                    }]
            session["members"] = members
            session["members_label"] = "、".join(
                m["name_zh"] for m in members
            ) if members else ""
            session["person_name_zh"] = session["members_label"]
            owner_label = ""
            owner_id = session.get("owner_user_id")
            if owner_id is not None:
                try:
                    from web.repositories import user_store

                    owner_profile = user_store.get_user_profile_by_id(int(owner_id))
                    owner_label = (
                        (owner_profile or {}).get("display_name")
                        or (owner_profile or {}).get("account_name")
                        or ""
                    )
                except Exception:
                    owner_label = ""
            session["owner_label"] = owner_label
            session["guests"] = list_session_guests(session_id)
            return session
    finally:
        conn.close()


def get_session_member_slugs(session_id: int) -> list[str]:
    session = get_session(session_id)
    if not session:
        return []
    return [m["person_slug"] for m in session.get("members", [])]


def _sources_from_chunk_ids(cur, chunk_ids: list[int]) -> list[dict[str, Any]]:
    if not chunk_ids:
        return []
    cur.execute(
        """
        SELECT c.id AS chunk_id, c.content, d.title, d.source_url, d.source_type
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE c.id = ANY(%s::int[]);
        """,
        (chunk_ids,),
    )
    by_id = {row["chunk_id"]: dict(row) for row in cur.fetchall()}
    out = []
    for cid in chunk_ids:
        row = by_id.get(cid)
        if not row:
            continue
        excerpt = (row.get("content") or "")[:1200]
        out.append({
            "chunk_id": cid,
            "title": row.get("title"),
            "source_type": row.get("source_type"),
            "source_url": row.get("source_url"),
            "content": excerpt,
            "similarity": None,
        })
    return out


def _unpack_message_sources(raw: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str | None]:
    if isinstance(raw, dict) and "sources" in raw:
        return (
            list(raw.get("sources") or []),
            list(raw.get("segments") or []),
            raw.get("phase"),
        )
    if isinstance(raw, list):
        return raw, [], None
    return [], [], None


def list_messages(session_id: int) -> list[dict[str, Any]]:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT m.id, m.role, m.content, m.created_at,
                       m.retrieved_chunk_ids, m.guest_id,
                       COALESCE(m.retrieval_sources, '[]'::jsonb) AS retrieval_sources,
                       COALESCE(p.slug, m.role) AS person_slug,
                       COALESCE(p.display_name_zh, p.name_zh) AS person_name_zh,
                       p.avatar_url AS avatar_url,
                       g.display_name AS guest_name
                FROM chat_messages m
                LEFT JOIN persons p ON p.id = m.person_id
                   OR (m.person_id IS NULL AND p.slug = m.role)
                LEFT JOIN chat_session_guests g ON g.id = m.guest_id
                WHERE m.session_id = %s
                ORDER BY m.created_at ASC;
                """,
                (session_id,),
            )
            out = []
            for r in cur.fetchall():
                msg = dict(r)
                raw_sources = msg.pop("retrieval_sources", None) or []
                if isinstance(raw_sources, str):
                    raw_sources = []
                if isinstance(raw_sources, dict):
                    if raw_sources.get("reply_to"):
                        msg["reply_to"] = raw_sources.get("reply_to")
                    if raw_sources.get("direct_reply"):
                        msg["direct_reply"] = bool(raw_sources.get("direct_reply"))
                sources, segments, meta_phase = _unpack_message_sources(raw_sources)
                chunk_ids = msg.get("retrieved_chunk_ids") or []
                if not sources and chunk_ids:
                    sources = _sources_from_chunk_ids(cur, list(chunk_ids))
                if sources and not segments and (msg.get("content") or "").strip():
                    try:
                        from web.conversations.discussion import parse_cited_reply

                        display, segments = parse_cited_reply(
                            msg["content"], sources
                        )
                        if segments:
                            msg["content"] = display
                    except Exception:
                        pass
                msg["sources"] = sources
                msg["content_segments"] = segments
                if meta_phase:
                    msg["phase"] = meta_phase

                if msg["role"] == "user":
                    if msg.get("guest_name"):
                        msg["person_name_zh"] = msg["guest_name"]
                        msg["is_guest"] = True
                    else:
                        msg["person_name_zh"] = None
                elif msg["role"] == "user_twin":
                    msg["person_name_zh"] = f"{USER_DISPLAY_NAME}（分身）"
                elif msg["role"] == "conclusion":
                    msg["person_name_zh"] = "討論結論"
                elif msg["role"] == "assistant" and msg.get("person_name_zh"):
                    pass
                elif msg["role"] not in ("user", "assistant", "moderator", "system"):
                    if not msg.get("person_name_zh"):
                        cur.execute(
                            "SELECT COALESCE(display_name_zh, name_zh) AS name_zh FROM persons WHERE slug = %s;",
                            (msg["role"],),
                        )
                        p = cur.fetchone()
                        if p:
                            msg["person_name_zh"] = p["name_zh"]
                            msg["person_slug"] = msg["role"]
                out.append(msg)
            return out
    finally:
        conn.close()


def update_session_summary(session_id: int, summary: str) -> None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE chat_sessions
                SET summary = %s
                WHERE id = %s;
                """,
                (summary, session_id),
            )
        conn.commit()
    finally:
        conn.close()


def add_message(
    session_id: int,
    role: str,
    content: str,
    person_slug: str | None = None,
    chunk_ids: list[int] | None = None,
    sources: list[dict[str, Any]] | Any | None = None,
    *,
    phase: str | None = None,
    content_segments: list[dict[str, Any]] | None = None,
    guest_id: int | None = None,
) -> dict[str, Any]:
    chunk_ids = chunk_ids or []
    if sources is None:
        sources_payload: Any = []
    elif isinstance(sources, dict):
        sources_payload = sources
    elif content_segments:
        sources_payload = {
            "sources": sources,
            "segments": content_segments,
            "phase": phase,
        }
    else:
        sources_payload = sources
    if phase and isinstance(sources_payload, list):
        sources_payload = {"sources": sources_payload, "segments": [], "phase": phase}
    elif phase and isinstance(sources_payload, dict) and "phase" not in sources_payload:
        sources_payload["phase"] = phase
    slug_for_person = person_slug or (
        role
        if role not in (
            "user",
            "user_twin",
            "assistant",
            "moderator",
            "system",
            "conclusion",
        )
        else None
    )
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            person_id = None
            name_zh = None
            if slug_for_person:
                cur.execute(
                    "SELECT id, COALESCE(display_name_zh, name_zh) AS name_zh FROM persons WHERE slug = %s;",
                    (slug_for_person,),
                )
                row = cur.fetchone()
                if row:
                    person_id = row["id"]
                    name_zh = row["name_zh"]

            store_role = slug_for_person if slug_for_person and role == "assistant" else role
            if role == "assistant" and slug_for_person:
                store_role = slug_for_person

            cur.execute(
                """
                INSERT INTO chat_messages (
                    session_id, person_id, role, content,
                    retrieved_chunk_ids, retrieval_sources, guest_id
                ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
                RETURNING id, role, content, created_at;
                """,
                (
                    session_id,
                    person_id,
                    store_role,
                    content.strip(),
                    chunk_ids,
                    Json(sources_payload),
                    guest_id,
                ),
            )
            msg = dict(cur.fetchone())
            msg["person_slug"] = slug_for_person
            msg["guest_id"] = guest_id
            if role == "user" and guest_id:
                cur.execute(
                    "SELECT display_name FROM chat_session_guests WHERE id = %s;",
                    (guest_id,),
                )
                g = cur.fetchone()
                if g:
                    msg["person_name_zh"] = g["display_name"]
                    msg["is_guest"] = True
            elif role == "user_twin":
                msg["person_name_zh"] = f"{USER_DISPLAY_NAME}（分身）"
            elif role == "conclusion":
                msg["person_name_zh"] = "討論結論"
            else:
                msg["person_name_zh"] = name_zh
            unpacked, segments, meta_phase = _unpack_message_sources(sources_payload)
            msg["sources"] = unpacked
            msg["content_segments"] = segments
            if meta_phase:
                msg["phase"] = meta_phase
        conn.commit()
        return msg
    finally:
        conn.close()


def load_session_insights(session_id: int) -> dict[str, Any] | None:
    """讀取討論室已儲存的心智圖／重點（重啟後仍可用）。"""
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT session_id, message_count, llm_message_count, insights, updated_at
                FROM chat_session_insights
                WHERE session_id = %s;
                """,
                (session_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            out = dict(row)
            raw = out.get("insights")
            if isinstance(raw, str):
                import json

                try:
                    out["insights"] = json.loads(raw)
                except json.JSONDecodeError:
                    out["insights"] = {}
            elif raw is None:
                out["insights"] = {}
            return out
    finally:
        conn.close()


def save_session_insights(
    session_id: int,
    message_count: int,
    insights: dict[str, Any],
    *,
    llm_message_count: int = 0,
) -> None:
    """將心智圖、發言重點、立場圖寫入資料庫。"""
    payload = dict(insights)
    payload.pop("message_count", None)
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_session_insights (
                    session_id, message_count, llm_message_count, insights, updated_at
                )
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (session_id) DO UPDATE SET
                    message_count = EXCLUDED.message_count,
                    llm_message_count = EXCLUDED.llm_message_count,
                    insights = EXCLUDED.insights,
                    updated_at = NOW();
                """,
                (session_id, message_count, llm_message_count, Json(payload)),
            )
        conn.commit()
    finally:
        conn.close()
