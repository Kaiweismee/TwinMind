"""會員帳號與登入 session（PostgreSQL）"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from config import DB_CONFIG  # type: ignore
from session_auth import hash_password, new_guest_token, verify_password

AUTH_SESSION_DAYS = int(os.getenv("AUTH_SESSION_DAYS", "30"))
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

DEFAULT_TWIN_CONTEXT = """
你是使用者的數位分身「{name}」。
說話風格：務實、願意承認不確定、會用生活例子，繁體中文，不要太官腔。
目前知識庫尚在建置，可根據使用者自我介紹發言，勿捏造具體新聞日期或統計數字。
""".strip()

MAX_TWINS_PER_USER = 8

TWIN_PRESETS: dict[str, dict[str, str]] = {
    "life": {
        "name": "生活",
        "twin_context": (
            "你是使用者「{owner_name}」的「生活」數位分身。\n"
            "場景：日常聊天、興趣、人際、休閒。\n"
            "風格：輕鬆自然、像朋友聊天，繁體中文，約 100～150 字。"
        ),
    },
    "student": {
        "name": "學生",
        "twin_context": (
            "你是使用者「{owner_name}」的「學生」數位分身。\n"
            "場景：課業、研究、學習方法、升學與知識探索。\n"
            "風格：好奇、條理清楚、願意舉例，繁體中文，約 100～150 字。"
        ),
    },
    "company": {
        "name": "公司",
        "twin_context": (
            "你是使用者「{owner_name}」的「公司／職場」數位分身。\n"
            "場景：工作匯報、商業決策、團隊協作、職涯發展。\n"
            "風格：專業務實、結構化表達，繁體中文，約 100～150 字。"
        ),
    },
    "custom": {
        "name": "自訂",
        "twin_context": DEFAULT_TWIN_CONTEXT,
    },
}

REGISTER_AVATAR_PRESETS = {
    "/static/avatars/user-preset-1.svg",
    "/static/avatars/user-preset-2.svg",
    "/static/avatars/user-preset-3.svg",
    "/static/avatars/user-preset-4.svg",
}


def is_valid_register_avatar_preset(avatar_url: str) -> bool:
    return (avatar_url or "").strip() in REGISTER_AVATAR_PRESETS


def _conn():
    return psycopg2.connect(**DB_CONFIG)


def ensure_user_schema() -> None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    bio TEXT NOT NULL DEFAULT '',
                    avatar_url TEXT,
                    twin_context TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_auth_sessions (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL
                        REFERENCES users(id) ON DELETE CASCADE,
                    token TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    expires_at TIMESTAMPTZ NOT NULL
                );
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_auth_sessions_token
                ON user_auth_sessions(token);
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_auth_sessions_user
                ON user_auth_sessions(user_id);
                """
            )
            cur.execute(
                """
                ALTER TABLE chat_sessions
                ADD COLUMN IF NOT EXISTS owner_user_id INTEGER
                    REFERENCES users(id) ON DELETE SET NULL;
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_sessions_owner_user
                ON chat_sessions(owner_user_id)
                WHERE owner_user_id IS NOT NULL;
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_twins (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL
                        REFERENCES users(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    preset TEXT NOT NULL DEFAULT 'custom',
                    bio TEXT NOT NULL DEFAULT '',
                    twin_context TEXT NOT NULL DEFAULT '',
                    avatar_url TEXT,
                    sort_order SMALLINT NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_twins_user
                ON user_twins(user_id, sort_order);
                """
            )
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS active_twin_id INTEGER
                    REFERENCES user_twins(id) ON DELETE SET NULL;
                """
            )
        conn.commit()
        _ensure_default_twins_for_all_users()
    finally:
        conn.close()


def _normalize_username(username: str) -> str:
    return username.strip().lower()


def _validate_register(
    *,
    email: str,
    username: str,
    password: str,
    display_name: str | None,
) -> tuple[str, str, str, str]:
    email = email.strip().lower()
    username = _normalize_username(username)
    password = password or ""
    display_name = (display_name or "").strip() or username

    if not EMAIL_RE.match(email):
        raise ValueError("請輸入有效的 Email")
    if not USERNAME_RE.match(username):
        raise ValueError("使用者名稱需 3–32 字，僅限英文、數字、底線")
    if len(password) < 8:
        raise ValueError("密碼至少 8 個字元")
    if len(display_name) > 64:
        raise ValueError("顯示名稱過長")
    return email, username, password, display_name


def _user_public(row: dict[str, Any]) -> dict[str, Any]:
    name = row.get("display_name") or row.get("username") or "使用者"
    twin = (row.get("twin_context") or "").strip()
    if not twin:
        twin = DEFAULT_TWIN_CONTEXT.format(name=name)
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "account_name": name,
        "display_name": name,
        "bio": row.get("bio") or "",
        "avatar_url": row.get("avatar_url") or "/static/icon.png",
        "avatar_letter": name[:1].upper() or "U",
        "twin_context": twin,
        "active_twin_id": row.get("active_twin_id"),
        "twin_name": None,
        "twins": [],
    }


def _twin_public(row: dict[str, Any], *, active: bool = False) -> dict[str, Any]:
    name = row.get("name") or "分身"
    return {
        "id": row["id"],
        "name": name,
        "preset": row.get("preset") or "custom",
        "bio": row.get("bio") or "",
        "twin_context": row.get("twin_context") or "",
        "avatar_url": row.get("avatar_url"),
        "is_active": active,
    }


def _preset_context(preset: str, owner_name: str, twin_name: str) -> str:
    key = (preset or "custom").strip().lower()
    template = TWIN_PRESETS.get(key, TWIN_PRESETS["custom"])["twin_context"]
    return template.format(owner_name=owner_name, name=twin_name)


def _ensure_default_twins_for_all_users() -> None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT id, display_name, active_twin_id FROM users;")
            users = cur.fetchall()
            for user in users:
                cur.execute(
                    "SELECT COUNT(*)::int AS n FROM user_twins WHERE user_id = %s;",
                    (user["id"],),
                )
                if cur.fetchone()["n"] > 0:
                    continue
                _insert_default_twins(cur, user["id"], user["display_name"])
                if not user.get("active_twin_id"):
                    cur.execute(
                        """
                        UPDATE users SET active_twin_id = (
                            SELECT id FROM user_twins
                            WHERE user_id = %s AND preset = 'life'
                            LIMIT 1
                        )
                        WHERE id = %s;
                        """,
                        (user["id"], user["id"]),
                    )
        conn.commit()
    finally:
        conn.close()


def _insert_initial_twin(cur, user_id: int, owner_name: str, preset: str) -> int:
    preset_key = (preset or "life").strip().lower()
    if preset_key not in ("life", "student", "company"):
        preset_key = "life"
    meta = TWIN_PRESETS[preset_key]
    twin_name = meta["name"]
    cur.execute(
        """
        INSERT INTO user_twins (
            user_id, name, preset, bio, twin_context, sort_order
        )
        VALUES (%s, %s, %s, '', %s, 0)
        RETURNING id;
        """,
        (
            user_id,
            twin_name,
            preset_key,
            _preset_context(preset_key, owner_name, twin_name),
        ),
    )
    row = cur.fetchone()
    return int(row["id"] if isinstance(row, dict) else row[0])


def _insert_default_twins(cur, user_id: int, owner_name: str) -> None:
    order = 0
    for preset in ("life", "student", "company"):
        meta = TWIN_PRESETS[preset]
        twin_name = meta["name"]
        cur.execute(
            """
            INSERT INTO user_twins (
                user_id, name, preset, bio, twin_context, sort_order
            )
            VALUES (%s, %s, %s, '', %s, %s);
            """,
            (
                user_id,
                twin_name,
                preset,
                _preset_context(preset, owner_name, twin_name),
                order,
            ),
        )
        order += 1


def list_user_twins(user_id: int) -> list[dict[str, Any]]:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT active_twin_id FROM users WHERE id = %s;",
                (user_id,),
            )
            user = cur.fetchone()
            active_id = user["active_twin_id"] if user else None
            cur.execute(
                """
                SELECT * FROM user_twins
                WHERE user_id = %s
                ORDER BY sort_order, id;
                """,
                (user_id,),
            )
            return [
                _twin_public(dict(r), active=r["id"] == active_id)
                for r in cur.fetchall()
            ]
    finally:
        conn.close()


def _get_active_twin_row(user_id: int, active_twin_id: int | None) -> dict[str, Any] | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if active_twin_id:
                cur.execute(
                    """
                    SELECT * FROM user_twins
                    WHERE id = %s AND user_id = %s;
                    """,
                    (active_twin_id, user_id),
                )
                row = cur.fetchone()
                if row:
                    return dict(row)
            cur.execute(
                """
                SELECT * FROM user_twins
                WHERE user_id = %s
                ORDER BY sort_order, id
                LIMIT 1;
                """,
                (user_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def build_user_profile(row: dict[str, Any]) -> dict[str, Any]:
    profile = _user_public(row)
    twins = list_user_twins(profile["id"])
    profile["twins"] = twins
    active = next((t for t in twins if t["is_active"]), twins[0] if twins else None)
    if active:
        profile["active_twin_id"] = active["id"]
        profile["twin_name"] = active["name"]
        profile["display_name"] = f"{profile['account_name']}（{active['name']}）"
        profile["twin_context"] = active["twin_context"] or profile["twin_context"]
        if active.get("bio"):
            profile["bio"] = active["bio"]
        if active.get("avatar_url"):
            profile["avatar_url"] = active["avatar_url"]
        profile["avatar_letter"] = active["name"][:1].upper() or profile["avatar_letter"]
    return profile


def create_twin(
    user_id: int,
    *,
    name: str,
    preset: str = "custom",
    bio: str = "",
    twin_context: str | None = None,
) -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("請輸入分身名稱")
    if len(name) > 32:
        raise ValueError("分身名稱過長")

    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT display_name FROM users WHERE id = %s;",
                (user_id,),
            )
            user = cur.fetchone()
            if not user:
                raise ValueError("找不到使用者")
            cur.execute(
                "SELECT COUNT(*)::int AS n FROM user_twins WHERE user_id = %s;",
                (user_id,),
            )
            if cur.fetchone()["n"] >= MAX_TWINS_PER_USER:
                raise ValueError(f"最多 {MAX_TWINS_PER_USER} 個分身")

            preset_key = (preset or "custom").strip().lower()
            if preset_key not in TWIN_PRESETS:
                preset_key = "custom"
            if preset_key in ("life", "student", "company"):
                cur.execute(
                    """
                    SELECT 1 FROM user_twins
                    WHERE user_id = %s AND preset = %s;
                    """,
                    (user_id, preset_key),
                )
                if cur.fetchone():
                    label = TWIN_PRESETS[preset_key]["name"]
                    raise ValueError(f"已有「{label}」類別的分身")
            ctx = (twin_context or "").strip() or _preset_context(
                preset_key, user["display_name"], name
            )
            cur.execute(
                """
                INSERT INTO user_twins (
                    user_id, name, preset, bio, twin_context, sort_order
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    COALESCE(
                        (SELECT MAX(sort_order) + 1 FROM user_twins WHERE user_id = %s),
                        0
                    )
                )
                RETURNING *;
                """,
                (user_id, name, preset_key, bio or "", ctx, user_id),
            )
            row = dict(cur.fetchone())
        conn.commit()
        twins = list_user_twins(user_id)
        active_id = next((t["id"] for t in twins if t["is_active"]), None)
        return _twin_public(row, active=row["id"] == active_id)
    finally:
        conn.close()


def activate_twin(user_id: int, twin_id: int) -> dict[str, Any]:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT 1 FROM user_twins
                WHERE id = %s AND user_id = %s;
                """,
                (twin_id, user_id),
            )
            if not cur.fetchone():
                raise ValueError("找不到此分身")
            cur.execute(
                "UPDATE users SET active_twin_id = %s WHERE id = %s RETURNING *;",
                (twin_id, user_id),
            )
            row = dict(cur.fetchone())
        conn.commit()
        return build_user_profile(row)
    finally:
        conn.close()


def get_user_profile_by_id(user_id: int) -> dict[str, Any] | None:
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE id = %s;", (user_id,))
            row = cur.fetchone()
            if not row:
                return None
            return build_user_profile(dict(row))
    finally:
        conn.close()


def register_user(
    *,
    email: str,
    username: str,
    password: str,
    display_name: str | None = None,
    initial_preset: str = "life",
    avatar_url: str | None = None,
) -> dict[str, Any]:
    email, username, password, display_name = _validate_register(
        email=email,
        username=username,
        password=password,
        display_name=display_name,
    )
    pwd_hash = hash_password(password)
    twin = DEFAULT_TWIN_CONTEXT.format(name=display_name)
    preset_avatar = (avatar_url or "").strip()
    if preset_avatar and preset_avatar not in REGISTER_AVATAR_PRESETS:
        raise ValueError("頭像選項無效")

    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT 1 FROM users WHERE email = %s;", (email,))
            if cur.fetchone():
                raise ValueError("此 Email 已被註冊")
            cur.execute("SELECT 1 FROM users WHERE username = %s;", (username,))
            if cur.fetchone():
                raise ValueError("此使用者名稱已被使用")
            cur.execute(
                """
                INSERT INTO users (
                    username, email, password_hash, display_name, bio, twin_context, avatar_url
                )
                VALUES (%s, %s, %s, %s, '', %s, %s)
                RETURNING *;
                """,
                (username, email, pwd_hash, display_name, twin, preset_avatar or None),
            )
            row = dict(cur.fetchone())
            user_id = row["id"]
            twin_id = _insert_initial_twin(cur, user_id, display_name, initial_preset)
            cur.execute(
                """
                UPDATE users SET active_twin_id = %s
                WHERE id = %s
                RETURNING *;
                """,
                (twin_id, user_id),
            )
            row = dict(cur.fetchone())
        conn.commit()
        return build_user_profile(row)
    finally:
        conn.close()


def update_user_profile(
    user_id: int,
    *,
    display_name: str | None = None,
    bio: str | None = None,
    avatar_url: str | None = None,
) -> dict[str, Any]:
    updates: list[str] = []
    params: list[Any] = []
    if display_name is not None:
        name = display_name.strip()
        if not name:
            raise ValueError("顯示名稱不可為空")
        if len(name) > 64:
            raise ValueError("顯示名稱過長")
        updates.append("display_name = %s")
        params.append(name)
    if bio is not None:
        updates.append("bio = %s")
        params.append(bio.strip()[:2000])
    if avatar_url is not None:
        updates.append("avatar_url = %s")
        params.append((avatar_url or "").strip() or None)
    if not updates:
        row = get_user_profile_by_id(user_id)
        if not row:
            raise ValueError("找不到使用者")
        return row
    updates.append("updated_at = NOW()")
    params.append(user_id)
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = %s RETURNING *;",
                params,
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("找不到使用者")
            result = build_user_profile(dict(row))
        conn.commit()
        return result
    finally:
        conn.close()


def authenticate_user(login: str, password: str) -> dict[str, Any]:
    login = (login or "").strip().lower()
    password = password or ""
    if not login or not password:
        raise ValueError("請輸入帳號與密碼")

    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT * FROM users
                WHERE email = %s OR username = %s
                LIMIT 1;
                """,
                (login, login),
            )
            row = cur.fetchone()
            if not row or not verify_password(password, row["password_hash"]):
                raise ValueError("帳號或密碼錯誤")
            return build_user_profile(dict(row))
    finally:
        conn.close()


def create_auth_session(user_id: int) -> tuple[str, datetime]:
    token = new_guest_token()
    expires = datetime.now(timezone.utc) + timedelta(days=AUTH_SESSION_DAYS)
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_auth_sessions (user_id, token, expires_at)
                VALUES (%s, %s, %s);
                """,
                (user_id, token, expires),
            )
        conn.commit()
        return token, expires
    finally:
        conn.close()


def delete_auth_session(token: str) -> None:
    if not token:
        return
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM user_auth_sessions WHERE token = %s;",
                (token.strip(),),
            )
        conn.commit()
    finally:
        conn.close()


def get_user_by_token(token: str | None) -> dict[str, Any] | None:
    token = (token or "").strip()
    if not token:
        return None
    conn = _conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT u.*
                FROM user_auth_sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token = %s AND s.expires_at > NOW()
                LIMIT 1;
                """,
                (token,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return build_user_profile(dict(row))
    finally:
        conn.close()


def get_session_owner_user_id(session_id: int) -> int | None:
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT owner_user_id FROM chat_sessions WHERE id = %s;",
                (session_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return row[0]
    finally:
        conn.close()
