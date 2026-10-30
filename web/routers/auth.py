"""帳號 API：查詢登入狀態、註冊、登入與登出。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from web.core.dependencies import _clear_auth_cookie, _profile_for_user, _set_auth_cookie, get_optional_user
from web.repositories import user_store
from web.schemas.requests import LoginRequest, RegisterRequest
from web.services.knowledge import _sync_user_rag
from web.core.settings import AUTH_COOKIE


router = APIRouter()


@router.get("/api/auth/me")
def api_auth_me(user: dict[str, Any] | None = Depends(get_optional_user)):
    if not user:
        return {"authenticated": False}
    profile = _profile_for_user(user)
    _sync_user_rag(user)
    return {"authenticated": True, "user": profile}


@router.post("/api/auth/register")
def api_register(body: RegisterRequest, response: Response):
    try:
        user = user_store.register_user(
            email=body.email,
            username=body.username,
            password=body.password,
            display_name=body.display_name or None,
            initial_preset=body.initial_preset,
            avatar_url=body.avatar_preset or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    token, _expires = user_store.create_auth_session(user["id"])
    _set_auth_cookie(response, token)
    profile = _profile_for_user(user)
    _sync_user_rag(user)
    return {"user": profile}


@router.post("/api/auth/login")
def api_login(body: LoginRequest, response: Response):
    try:
        user = user_store.authenticate_user(body.login, body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    token, _expires = user_store.create_auth_session(user["id"])
    _set_auth_cookie(response, token)
    profile = _profile_for_user(user)
    _sync_user_rag(user)
    return {"user": profile}


@router.post("/api/auth/logout")
def api_logout(
    request: Request,
    response: Response,
    user: dict[str, Any] | None = Depends(get_optional_user),
):
    token = request.cookies.get(AUTH_COOKIE)
    if token:
        user_store.delete_auth_session(token)
    _clear_auth_cookie(response)
    return {"ok": True}
