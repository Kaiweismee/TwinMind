"""啟動工作：沿用既有建表流程與背景模型暖機。"""

from __future__ import annotations

import threading

from web.repositories import chat_store
from web.conversations import person_chat
from web.conversations import twin_chat
from web.repositories import user_store
from web.core.runtime import _log
from web.core.settings import PROFILE_AVATAR_ROOT


def _warm_embedding_model() -> None:
    try:
        from web.core.rag_backend import embed_texts

        embed_texts(["warmup"])
        _log.info("embedding model warmed up for topic recommend")
    except Exception as exc:
        _log.debug("embedding warmup skipped: %s", exc)


def startup():
    chat_store.ensure_chat_schema()
    user_store.ensure_user_schema()
    twin_chat.ensure_twin_chat_schema()
    person_chat.ensure_person_chat_schema()
    PROFILE_AVATAR_ROOT.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=_warm_embedding_model, daemon=True).start()
