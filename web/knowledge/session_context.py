"""討論室建立時上傳的參考檔案 → 寫入使用者知識庫並產生議題摘要。"""

from __future__ import annotations

from typing import Any

from web.conversations import twin_chat
from web.knowledge import user_rag

MAX_SESSION_FILES = 6
MAX_BRIEF_CHARS = 16000


def _attachment_body(att: dict[str, Any]) -> str:
    return user_rag._message_body("", [att])  # noqa: SLF001 — 與分身對話共用解析


def ingest_session_files(
    user_id: int,
    session_id: int,
    topic: str,
    files: list[tuple[str, bytes]],
    *,
    display_name: str = "使用者",
) -> dict[str, Any]:
    """
    儲存檔案、寫入 RAG（source_type=session_context）、回傳 context_brief 供討論注入。
    """
    if len(files) > MAX_SESSION_FILES:
        raise ValueError(f"最多上傳 {MAX_SESSION_FILES} 個檔案")

    attachments: list[dict[str, Any]] = []
    bodies: list[str] = []
    ingested = 0

    for filename, data in files:
        if not filename or not data:
            continue
        att = twin_chat.save_upload(user_id, filename, data)
        att["session_id"] = session_id
        attachments.append(att)
        body = _attachment_body(att)
        if body:
            bodies.append(body)
            user_rag.ingest_session_attachment(
                user_id,
                session_id,
                topic=topic,
                attachment=att,
                display_name=display_name,
            )
            ingested += 1

    brief = ""
    if bodies:
        joined = "\n\n".join(bodies)
        brief = f"【討論室參考資料（建立者上傳）】\n{joined}"[:MAX_BRIEF_CHARS]

    return {
        "context_brief": brief,
        "context_files": attachments,
        "ingested": ingested,
    }
