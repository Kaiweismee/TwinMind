"""AI 用戶端：檢查金鑰與建立對話用戶端。"""

from __future__ import annotations

import os

from fastapi import HTTPException


def _require_openai():
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key.startswith("sk-your"):
        raise HTTPException(
            status_code=400,
            detail="請在 .env 設定 OPENAI_API_KEY 才能取得名人回覆",
        )
    return api_key


def _discussion_client():
    api_key = _require_openai()
    from openai import OpenAI

    return OpenAI(api_key=api_key), os.getenv("OPENAI_MODEL", "gpt-4o-mini")
