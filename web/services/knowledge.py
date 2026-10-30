"""個人知識庫流程：登入後建立資料與補匯既有對話。"""

from __future__ import annotations

from typing import Any

from web.knowledge import user_rag


def _sync_user_rag(user: dict[str, Any]) -> None:
    """確保使用者知識庫存在，必要時補匯既有分身對話。"""
    try:
        uid = int(user["id"])
        name = user.get("display_name") or user.get("username") or "使用者"
        user_rag.ensure_user_person(uid, display_name=name)
        slug = user_rag.user_person_slug(uid)
        conn = user_rag._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM documents d
                    JOIN persons p ON p.id = d.person_id
                    WHERE p.slug = %s;
                    """,
                    (slug,),
                )
                doc_count = int(cur.fetchone()[0])
        finally:
            conn.close()
        if doc_count == 0:
            user_rag.backfill_user_knowledge(
                uid,
                display_name=name,
                twin_id=user.get("active_twin_id"),
            )
    except Exception:
        pass
