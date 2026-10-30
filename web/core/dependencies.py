"""共用驗證：登入使用者、Cookie、討論室存取與檢索筆數。"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request, Response

from web.core.rag_backend import DEFAULT_TOP_K
from web.repositories import chat_store
from web.repositories import user_store
from web.core.settings import AUTH_COOKIE, AUTH_COOKIE_MAX_AGE, AUTH_COOKIE_SECURE


def _set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=AUTH_COOKIE,
        value=token,
        max_age=AUTH_COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=AUTH_COOKIE_SECURE,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=AUTH_COOKIE, path="/")


def get_optional_user(request: Request) -> dict[str, Any] | None:
    return user_store.get_user_by_token(request.cookies.get(AUTH_COOKIE))


def require_user(
    user: dict[str, Any] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    if not user:
        raise HTTPException(status_code=401, detail="請先登入")
    return user


def _profile_for_user(user: dict[str, Any] | None) -> dict[str, Any]:
    if user:
        profile = dict(user)
        profile["rag_top_k"] = DEFAULT_TOP_K
        return profile
    profile = chat_store.get_profile()
    profile["rag_top_k"] = DEFAULT_TOP_K
    return profile


def _resolve_top_k(top_k: int | None) -> int:
    if top_k is None:
        return DEFAULT_TOP_K
    return top_k


def _enforce_session_access(
    session_id: int,
    *,
    x_session_owner: str | None = None,
    user: dict[str, Any] | None = None,
) -> None:
    is_owner = (x_session_owner or "").strip() == "1"
    ok, err = chat_store.check_session_access(
        session_id,
        is_owner=is_owner,
        user_id=user.get("id") if user else None,
    )
    if not ok:
        raise HTTPException(status_code=403, detail=err or "無權限進入此討論室")
