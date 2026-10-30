"""討論互動 API：下一輪、討論狀態與使用者插話。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Header

from web.core.dependencies import _enforce_session_access, _profile_for_user, require_user
from web.schemas.requests import DiscussRequest, SendMessageRequest, TurnRequest
from web.services.messages import send_message
from web.services.turns import _run_single_turn, _turn_state


router = APIRouter()


@router.get("/api/sessions/{session_id}/turn-state")
def api_turn_state(
    session_id: int,
    x_session_owner: str | None = Header(None, alias="X-Session-Owner"),
    user: dict[str, Any] = Depends(require_user),
):
    _enforce_session_access(
        session_id,
        x_session_owner=x_session_owner,
        user=user,
    )
    return _turn_state(session_id, profile=_profile_for_user(user))


@router.post("/api/sessions/{session_id}/turn")
def api_next_turn(
    session_id: int,
    body: TurnRequest | None = None,
    x_session_owner: str | None = Header(None, alias="X-Session-Owner"),
    user: dict[str, Any] = Depends(require_user),
):
    """一次只產生一則發言（你的分身 / 名人 / 結論）。"""
    _enforce_session_access(
        session_id,
        x_session_owner=x_session_owner,
        user=user,
    )
    body = body or TurnRequest()
    try:
        return _run_single_turn(
            session_id,
            top_k=body.top_k,
            profile=_profile_for_user(user),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/sessions/{session_id}/discuss")
def api_start_discussion(
    session_id: int,
    body: DiscussRequest | None = None,
    x_session_owner: str | None = Header(None, alias="X-Session-Owner"),
    user: dict[str, Any] = Depends(require_user),
):
    """相容舊版：等同於只執行一則 turn。"""
    _enforce_session_access(
        session_id,
        x_session_owner=x_session_owner,
        user=user,
    )
    body = body or DiscussRequest()
    return _run_single_turn(
        session_id,
        top_k=body.top_k,
        profile=_profile_for_user(user),
    )


@router.post("/api/sessions/{session_id}/messages")
def api_send_message(
    session_id: int,
    body: SendMessageRequest,
    x_session_owner: str | None = Header(None, alias="X-Session-Owner"),
    user: dict[str, Any] = Depends(require_user),
):
    """選填插話：有內容時會觸發新一輪辯論與結論。"""
    return send_message(
        session_id, body, x_session_owner=x_session_owner, user=user,
    )
