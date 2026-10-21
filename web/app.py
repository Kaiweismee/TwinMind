"""
數位分身 Web：FastAPI + 多人討論聊天室

啟動：
  cd ~/Desktop/digital_twin_project
  export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
  ./venv/bin/uvicorn web.app:app --reload --host 127.0.0.1 --port 8000

瀏覽器：http://127.0.0.1:8000
"""

from __future__ import annotations

import logging
import mimetypes
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

AUTH_COOKIE = "dt_auth"
AUTH_COOKIE_MAX_AGE = int(os.getenv("AUTH_SESSION_DAYS", "30")) * 86400
AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "").lower() in ("1", "true", "yes")

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

sys.path.insert(0, str(ROOT / "rag"))
sys.path.insert(0, str(Path(__file__).parent))

from search import format_context, search_chunks  # noqa: E402

import chat_store  # noqa: E402
import discussion  # noqa: E402
import discussion_insights  # noqa: E402
import person_chat  # noqa: E402
import twin_chat  # noqa: E402
import user_rag  # noqa: E402
import user_store  # noqa: E402
from config import DEFAULT_TOP_K  # noqa: E402

STATIC = Path(__file__).parent / "static"
PROFILE_AVATAR_ROOT = ROOT / "data" / "profile_avatars"
MAX_PROFILE_AVATAR_BYTES = int(os.getenv("PROFILE_AVATAR_MAX_BYTES", str(4 * 1024 * 1024)))
_log = logging.getLogger(__name__)
_RECOMMEND_POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="topic_recommend")
RECOMMEND_TIMEOUT_SEC = float(os.getenv("TOPIC_FIT_RECOMMEND_TIMEOUT", "75"))


def _rank_recommendations_openai(
    topic: str,
    persons: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    from topic_fit_llm import openai_configured, rank_persons_for_topic_llm

    if not openai_configured():
        raise HTTPException(
            status_code=503,
            detail="請在 .env 設定 OPENAI_API_KEY 以使用 AI 推薦名人",
        )

    fut = _RECOMMEND_POOL.submit(
        rank_persons_for_topic_llm, topic, persons, limit=limit
    )
    try:
        return fut.result(timeout=RECOMMEND_TIMEOUT_SEC)
    except FuturesTimeout as exc:
        _log.warning(
            "OpenAI topic recommend timed out after %.1fs",
            RECOMMEND_TIMEOUT_SEC,
        )
        raise HTTPException(
            status_code=504,
            detail="AI 推薦分析逾時，請稍後再試",
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        _log.warning("OpenAI topic recommend failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"AI 推薦失敗：{exc}",
        ) from exc


def _warm_embedding_model() -> None:
    try:
        from embedder import embed_texts

        embed_texts(["warmup"])
        _log.info("embedding model warmed up for topic recommend")
    except Exception as exc:
        _log.debug("embedding warmup skipped: %s", exc)


app = FastAPI(title="數位分身", version="2.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.on_event("startup")
def startup():
    chat_store.ensure_chat_schema()
    user_store.ensure_user_schema()
    twin_chat.ensure_twin_chat_schema()
    person_chat.ensure_person_chat_schema()
    PROFILE_AVATAR_ROOT.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=_warm_embedding_model, daemon=True).start()


def _safe_upload_name(name: str) -> str:
    base = os.path.basename(name or "avatar")
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in base)[:120]


def _profile_avatar_path(user_id: int, stored_name: str) -> Path:
    return PROFILE_AVATAR_ROOT / str(user_id) / _safe_upload_name(stored_name)


class CreateSessionRequest(BaseModel):
    person_slugs: list[str] = Field(default_factory=list)
    person_slug: str = ""  # 舊版單人 API 相容
    title: str = ""
    room_password: str = ""
    allow_guest_join: bool = True


class JoinSessionRequest(BaseModel):
    join_code: str
    password: str = ""
    guest_name: str = ""


class SendMessageRequest(BaseModel):
    content: str = ""
    reply_to: str = Field(
        default="all",
        description="溝通對象：all | user_twin | 名人 person_slug",
    )
    top_k: int | None = Field(
        default=None,
        ge=0,
        le=500,
        description="0 或不傳：依相似度取回全部相關段落；正整數則固定前 N 段",
    )


class DiscussRequest(BaseModel):
    top_k: int | None = Field(default=None, ge=0, le=500)


class TurnRequest(BaseModel):
    top_k: int | None = Field(default=None, ge=0, le=500)


class QueryRequest(BaseModel):
    question: str
    person: str
    top_k: int | None = Field(default=None, ge=0, le=500)
    types: str = ""


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    display_name: str = ""
    initial_preset: str = "life"
    avatar_preset: str = ""


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    bio: str | None = None


class ProfileAvatarPresetRequest(BaseModel):
    avatar_preset: str


class LoginRequest(BaseModel):
    login: str
    password: str


class CreateTwinRequest(BaseModel):
    name: str
    preset: str = "custom"
    bio: str = ""
    twin_context: str = ""


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


def _require_openai():
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key.startswith("sk-your"):
        raise HTTPException(
            status_code=400,
            detail="請在 .env 設定 OPENAI_API_KEY 才能取得名人回覆",
        )
    return api_key


@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@app.get("/lab")
def lab_page():
    """實驗室頁：媒體庫（顯示使用者上傳過的圖片與檔案）。"""
    path = STATIC / "rag-test.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="rag-test.html 不存在")
    return FileResponse(
        path,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/api/auth/me")
def api_auth_me(user: dict[str, Any] | None = Depends(get_optional_user)):
    if not user:
        return {"authenticated": False}
    profile = _profile_for_user(user)
    _sync_user_rag(user)
    return {"authenticated": True, "user": profile}


@app.post("/api/auth/register")
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


@app.post("/api/auth/login")
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


@app.post("/api/auth/logout")
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


@app.get("/api/twins")
def api_list_twins(user: dict[str, Any] = Depends(require_user)):
    twins = user_store.list_user_twins(user["id"])
    return {"twins": twins, "active_twin_id": user.get("active_twin_id")}


@app.post("/api/twins")
def api_create_twin(body: CreateTwinRequest, user: dict[str, Any] = Depends(require_user)):
    try:
        twin = user_store.create_twin(
            user["id"],
            name=body.name,
            preset=body.preset,
            bio=body.bio,
            twin_context=body.twin_context or None,
        )
        profile = user_store.get_user_profile_by_id(user["id"])
        return {"twin": twin, "user": _profile_for_user(profile)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/twins/{twin_id}/activate")
def api_activate_twin(twin_id: int, user: dict[str, Any] = Depends(require_user)):
    try:
        profile = user_store.activate_twin(user["id"], twin_id)
        return {"user": _profile_for_user(profile)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/twins/{twin_id}/context-files")
async def api_upload_twin_context_files(
    twin_id: int,
    files: list[UploadFile] = File(default=[]),
    user: dict[str, Any] = Depends(require_user),
):
    twins = user_store.list_user_twins(user["id"])
    if not any(int(t.get("id", -1)) == twin_id for t in twins):
        raise HTTPException(status_code=403, detail="無權限上傳到此分身")
    payload: list[dict[str, Any]] = []
    for f in files or []:
        if not f.filename:
            continue
        data = await f.read()
        if not data:
            continue
        try:
            payload.append(twin_chat.save_upload(user["id"], f.filename, data))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    if not payload:
        raise HTTPException(status_code=400, detail="請至少選擇一個檔案")

    msg = twin_chat.insert_message(
        user["id"],
        twin_id,
        role="user",
        content="（建立分身時上傳的個人文字資料）",
        attachments=payload,
    )
    try:
        user_rag.ingest_twin_chat_message(
            user["id"],
            twin_id,
            message_id=int(msg["id"]),
            role="user",
            content=msg.get("content") or "",
            attachments=payload,
            twin_name=next((t.get("name") for t in twins if int(t.get("id", -1)) == twin_id), "")
            or user.get("twin_name")
            or "分身",
            display_name=user.get("display_name") or user.get("username") or "使用者",
        )
    except Exception:
        pass
    return {"uploaded": len(payload), "files": payload}


@app.get("/api/twin-chat/messages")
def api_twin_chat_messages(user: dict[str, Any] = Depends(require_user)):
    twin_id = user.get("active_twin_id")
    if not twin_id:
        raise HTTPException(status_code=400, detail="請先選擇數位分身")
    messages = twin_chat.list_messages(user["id"], twin_id)
    return {"messages": messages, "twin_id": twin_id}


@app.get("/api/twin-chat/files/{user_id}/{stored_name}")
def api_twin_chat_file(
    user_id: int,
    stored_name: str,
    user: dict[str, Any] = Depends(require_user),
):
    if user["id"] != user_id:
        raise HTTPException(status_code=403, detail="無權限")
    path = twin_chat.get_upload_path(user_id, stored_name)
    if not path:
        raise HTTPException(status_code=404, detail="找不到檔案")
    return FileResponse(path)


@app.post("/api/twin-chat/messages")
async def api_twin_chat_send(
    content: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    user: dict[str, Any] = Depends(require_user),
):
    twin_id = user.get("active_twin_id")
    if not twin_id:
        raise HTTPException(status_code=400, detail="請先選擇數位分身")

    text = (content or "").strip()
    attachments: list[dict[str, Any]] = []
    for f in files or []:
        if not f.filename:
            continue
        data = await f.read()
        if not data:
            continue
        try:
            attachments.append(twin_chat.save_upload(user["id"], f.filename, data))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    if not text and not attachments:
        raise HTTPException(status_code=400, detail="請輸入訊息或上傳檔案")

    user_row = twin_chat.insert_message(
        user["id"],
        twin_id,
        role="user",
        content=text,
        attachments=attachments,
    )

    try:
        user_rag.ingest_twin_chat_message(
            user["id"],
            twin_id,
            message_id=int(user_row["id"]),
            role="user",
            content=text,
            attachments=attachments,
            twin_name=user.get("twin_name") or "分身",
            display_name=user.get("display_name") or user.get("username") or "使用者",
        )
    except Exception:
        pass

    try:
        api_key = _require_openai()
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        history = twin_chat.list_messages(user["id"], twin_id)
        reply = twin_chat.generate_reply(
            profile=user,
            twin_name=user.get("twin_name") or "分身",
            history=history[:-1],
            user_text=text,
            attachments=attachments,
            client=client,
            model=model,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    assistant_row = twin_chat.insert_message(
        user["id"],
        twin_id,
        role="assistant",
        content=reply,
        attachments=[],
    )
    return {"user_message": user_row, "assistant_message": assistant_row}


@app.get("/api/person-chat/threads")
def api_person_chat_threads(
    limit: int = Query(80, ge=1, le=200),
    user: dict[str, Any] = Depends(require_user),
):
    threads = person_chat.list_threads(user["id"], limit=limit)
    return {"threads": threads}


@app.delete("/api/person-chat/threads/{person_slug}")
def api_person_chat_delete_thread(
    person_slug: str,
    user: dict[str, Any] = Depends(require_user),
):
    slug = (person_slug or "").strip()
    if not slug:
        raise HTTPException(status_code=400, detail="缺少名人代號")
    deleted = person_chat.delete_thread(user["id"], slug)
    if not deleted:
        raise HTTPException(status_code=404, detail="找不到對話紀錄")
    return {"ok": True, "deleted": deleted}


@app.get("/api/person-chat/messages")
def api_person_chat_messages(
    person_slug: str = Query(..., min_length=1),
    user: dict[str, Any] = Depends(require_user),
):
    slug = person_slug.strip()
    person = person_chat.get_person(slug)
    if not person:
        raise HTTPException(status_code=404, detail="找不到名人")
    messages = person_chat.list_messages(user["id"], slug)
    return {"messages": messages, "person": person}


@app.post("/api/person-chat/messages")
async def api_person_chat_send(
    person_slug: str = Form(...),
    content: str = Form(""),
    files: list[UploadFile] = File(default=[]),
    user: dict[str, Any] = Depends(require_user),
):
    slug = (person_slug or "").strip()
    if not slug:
        raise HTTPException(status_code=400, detail="缺少名人代號")
    person = person_chat.get_person(slug)
    if not person:
        raise HTTPException(status_code=404, detail="找不到名人")

    text = (content or "").strip()
    attachments: list[dict[str, Any]] = []
    for f in files or []:
        if not f.filename:
            continue
        data = await f.read()
        if not data:
            continue
        try:
            attachments.append(twin_chat.save_upload(user["id"], f.filename, data))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    if not text and not attachments:
        raise HTTPException(status_code=400, detail="請輸入訊息或上傳檔案")

    user_row = person_chat.insert_message(
        user["id"],
        slug,
        role="user",
        content=text,
        attachments=attachments,
    )

    try:
        api_key = _require_openai()
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        history = person_chat.list_messages(user["id"], slug)
        reply = person_chat.generate_reply(
            person=person,
            history=history[:-1],
            user_text=text,
            attachments=attachments,
            client=client,
            model=model,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    assistant_row = person_chat.insert_message(
        user["id"],
        slug,
        role="assistant",
        content=reply,
    )
    return {"user_message": user_row, "assistant_message": assistant_row, "person": person}


@app.get("/api/media-library")
def api_media_library(
    limit: int = Query(500, ge=1, le=1200),
    user: dict[str, Any] = Depends(require_user),
):
    twin_items = twin_chat.list_user_media_files(user["id"], limit=min(limit, 600))
    person_items = person_chat.list_user_media_files(user["id"], limit=min(limit, 300))
    session_items = chat_store.list_user_session_media_files(
        user["id"], limit=min(limit, 300)
    )
    merged = twin_items + person_items + session_items
    merged.sort(
        key=lambda x: x.get("created_at") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    merged = merged[:limit]
    return {
        "items": merged,
        "count": len(merged),
        "image_count": sum(1 for i in merged if (i.get("file") or {}).get("kind") == "image"),
        "file_count": sum(1 for i in merged if (i.get("file") or {}).get("kind") != "image"),
    }


@app.get("/api/profile")
def api_profile(user: dict[str, Any] = Depends(require_user)):
    return _profile_for_user(user)


@app.patch("/api/profile")
def api_update_profile(
    body: UpdateProfileRequest,
    user: dict[str, Any] = Depends(require_user),
):
    try:
        profile = user_store.update_user_profile(
            user["id"],
            display_name=body.display_name,
            bio=body.bio,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"user": _profile_for_user(profile)}


@app.post("/api/profile/avatar/preset")
def api_set_profile_avatar_preset(
    body: ProfileAvatarPresetRequest,
    user: dict[str, Any] = Depends(require_user),
):
    avatar_preset = (body.avatar_preset or "").strip()
    if not user_store.is_valid_register_avatar_preset(avatar_preset):
        raise HTTPException(status_code=400, detail="頭像選項無效")
    profile = user_store.update_user_profile(user["id"], avatar_url=avatar_preset)
    return {"avatar_url": avatar_preset, "user": _profile_for_user(profile)}


@app.post("/api/profile/avatar")
async def api_upload_profile_avatar(
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(require_user),
):
    filename = _safe_upload_name(file.filename or "avatar")
    ext = Path(filename).suffix.lower()
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="請選擇圖片檔案")
    if len(data) > MAX_PROFILE_AVATAR_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"頭像檔案過大（上限 {MAX_PROFILE_AVATAR_BYTES // (1024 * 1024)} MB）",
        )
    mime = (
        file.content_type
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream"
    )
    if not mime.startswith("image/"):
        raise HTTPException(status_code=400, detail="僅支援圖片檔案")
    if not ext:
        ext = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
            "image/gif": ".gif",
        }.get(mime, ".png")

    stored_name = f"{uuid4().hex}{ext}"
    dst = _profile_avatar_path(user["id"], stored_name)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)

    avatar_url = f"/api/profile/avatar/{user['id']}/{stored_name}"
    profile = user_store.update_user_profile(user["id"], avatar_url=avatar_url)
    return {"avatar_url": avatar_url, "user": _profile_for_user(profile)}


@app.get("/api/profile/avatar/{user_id}/{stored_name}")
def api_profile_avatar_file(user_id: int, stored_name: str):
    path = _profile_avatar_path(user_id, stored_name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="找不到頭像")
    return FileResponse(path)


@app.get("/api/persons")
def list_persons():
    from data.person_profiles import PERSON_CATEGORIES

    return {
        "persons": chat_store.list_persons_feed(),
        "categories": [
            {"id": c["id"], "title": c["title"], "slugs": c["slugs"]}
            for c in PERSON_CATEGORIES
        ],
    }


@app.get("/api/persons/recommend")
def api_recommend_persons(
    topic: str = Query("", description="討論主題"),
    limit: int = Query(41, ge=1, le=50),
    fast: bool = Query(False, description="僅資料庫語意+關鍵字，不呼叫 OpenAI"),
):
    topic = (topic or "").strip()
    if len(topic) < 2:
        return {"recommendations": [], "topic": topic, "mode": "empty"}
    persons = chat_store.list_persons_feed()
    if fast:
        from topic_fit import rank_persons_for_topic

        ranked = rank_persons_for_topic(topic, persons, limit=limit)
        return {"recommendations": ranked, "topic": topic, "mode": "hybrid"}
    ranked = _rank_recommendations_openai(topic, persons, limit=limit)
    return {"recommendations": ranked, "topic": topic, "mode": "openai"}


@app.get("/api/sessions")
def api_sessions(
    ids: str = Query("", description="逗號分隔的聊天室 id（本機已建立/已加入）"),
    include_public: bool = Query(False, description="保留欄位（目前未使用）"),
    user: dict[str, Any] = Depends(require_user),
):
    session_ids: list[int] = []
    if ids.strip():
        for part in ids.split(","):
            part = part.strip()
            if part.isdigit():
                session_ids.append(int(part))
    sessions = chat_store.list_sessions(
        session_ids=session_ids or None,
        public_only=False,
        owner_user_id=(user["id"] if not session_ids else None),
    )
    return {"sessions": sessions}


@app.get("/api/notifications")
def api_notifications(
    ids: str = Query("", description="房主擁有的 session id，逗號分隔"),
    unread_only: bool = Query(True),
    user: dict[str, Any] = Depends(require_user),
):
    session_ids = [
        int(p.strip()) for p in ids.split(",") if p.strip().isdigit()
    ]
    owner_user_id = user.get("id") if not session_ids else None
    items = chat_store.list_join_notifications(
        session_ids,
        unread_only=unread_only,
        owner_user_id=owner_user_id,
    )
    unread_count = chat_store.count_unread_notifications(
        session_ids,
        owner_user_id=owner_user_id,
    )
    return {"notifications": items, "unread_count": unread_count}


class MarkNotificationsReadRequest(BaseModel):
    session_ids: list[int] = Field(default_factory=list)
    notification_ids: list[int] = Field(default_factory=list)


@app.post("/api/notifications/read")
def api_mark_notifications_read(
    body: MarkNotificationsReadRequest,
    user: dict[str, Any] = Depends(require_user),
):
    owner_user_id = (
        user.get("id") if not body.session_ids and not body.notification_ids else None
    )
    n = chat_store.mark_notifications_read(
        session_ids=body.session_ids or None,
        notification_ids=body.notification_ids or None,
        owner_user_id=owner_user_id,
    )
    return {"marked": n}


@app.get("/api/sessions/all-ids")
def api_all_session_ids():
    """一次性遷移：把既有聊天室 id 存進本機"""
    return {"ids": chat_store.list_all_session_ids()}


@app.post("/api/sessions")
def api_create_session(
    body: CreateSessionRequest,
    user: dict[str, Any] = Depends(require_user),
):
    slugs = [s.strip() for s in body.person_slugs if s.strip()]
    if not slugs and body.person_slug.strip():
        slugs = [body.person_slug.strip()]
    if not slugs:
        raise HTTPException(status_code=400, detail="請至少選擇一位名人")
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="請輸入討論主題")
    try:
        pwd = body.room_password.strip() if body.allow_guest_join else ""
        session = chat_store.create_session(
            slugs,
            body.title.strip(),
            room_password=pwd or None,
            owner_user_id=user["id"],
            allow_guest_join=body.allow_guest_join,
        )
        return {"session": session}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.post("/api/sessions/{session_id}/context")
async def api_upload_session_context(
    session_id: int,
    files: list[UploadFile] = File(default=[]),
    user: dict[str, Any] = Depends(require_user),
):
    """建立討論室後上傳參考檔案，供名人與分身依資料討論。"""
    owner_id = user_store.get_session_owner_user_id(session_id)
    if owner_id is None or owner_id != user["id"]:
        raise HTTPException(status_code=403, detail="僅房主可上傳參考資料")

    session = chat_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="找不到聊天室")

    import session_context  # noqa: WPS433

    payload: list[tuple[str, bytes]] = []
    for f in files or []:
        if not f.filename:
            continue
        data = await f.read()
        if data:
            payload.append((f.filename, data))
    if not payload:
        raise HTTPException(status_code=400, detail="請選擇至少一個檔案")

    try:
        result = session_context.ingest_session_files(
            user["id"],
            session_id,
            session.get("topic") or "",
            payload,
            display_name=user.get("display_name") or user.get("account_name") or "使用者",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    chat_store.update_session_context(
        session_id,
        context_brief=result.get("context_brief") or "",
        context_files=result.get("context_files") or [],
    )
    return {
        "session_id": session_id,
        "context_brief": result.get("context_brief") or "",
        "context_files": result.get("context_files") or [],
        "ingested": result.get("ingested", 0),
    }


class PinSessionRequest(BaseModel):
    pinned: bool = True


@app.patch("/api/sessions/{session_id}/pin")
def api_pin_session(
    session_id: int,
    body: PinSessionRequest,
    x_session_owner: str | None = Header(None, alias="X-Session-Owner"),
    user: dict[str, Any] = Depends(require_user),
):
    _enforce_session_access(
        session_id,
        x_session_owner=x_session_owner,
        user=user,
    )
    row = chat_store.set_session_pinned(session_id, body.pinned)
    if not row:
        raise HTTPException(status_code=404, detail="找不到聊天室")
    return {"session_id": session_id, "pinned": row["pinned"]}


@app.delete("/api/sessions/{session_id}")
def api_delete_session(
    session_id: int,
    user: dict[str, Any] = Depends(require_user),
):
    deleted = chat_store.delete_session_for_user(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="找不到聊天室")
    return {"ok": True, "session_id": session_id}


@app.get("/api/sessions/preview/{join_code}")
def api_session_preview(join_code: str, user: dict[str, Any] = Depends(require_user)):
    preview = chat_store.get_session_by_join_code(join_code)
    if not preview:
        raise HTTPException(status_code=404, detail="找不到此加入碼")
    return {
        "id": preview["id"],
        "topic": preview["topic"],
        "join_code": preview["join_code"],
        "has_password": preview.get("has_password", False),
        "members_label": preview.get("members_label", ""),
    }


@app.post("/api/sessions/join")
def api_join_session(body: JoinSessionRequest, user: dict[str, Any] = Depends(require_user)):
    try:
        return chat_store.join_session_for_user(
            body.join_code.strip(),
            int(user["id"]),
            display_name=body.guest_name.strip() or None,
            password=body.password.strip() or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/sessions/{session_id}")
def api_get_session(
    session_id: int,
    x_session_owner: str | None = Header(None, alias="X-Session-Owner"),
    user: dict[str, Any] = Depends(require_user),
):
    _enforce_session_access(
        session_id,
        x_session_owner=x_session_owner,
        user=user,
    )
    session = chat_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="找不到聊天室")
    messages = chat_store.list_messages(session_id)
    return {"session": session, "messages": messages}


def _discussion_client():
    api_key = _require_openai()
    from openai import OpenAI

    return OpenAI(api_key=api_key), os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def _run_single_turn(
    session_id: int,
    *,
    top_k: int | None = None,
    discussion_brief: str | None = None,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    session = chat_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="找不到聊天室")

    members = session.get("members") or []
    if not members:
        raise HTTPException(status_code=400, detail="此聊天室沒有參與的名人")

    client, model = _discussion_client()
    profile = profile or chat_store.get_profile()
    user_name = profile.get("display_name") or "你"
    topic = session.get("topic") or "討論"
    messages = chat_store.list_messages(session_id)

    merged_brief = discussion_brief
    ctx = (session.get("context_brief") or "").strip()
    if ctx:
        merged_brief = f"{ctx}\n\n{merged_brief}" if merged_brief else ctx

    msg = discussion.run_next_turn(
        session_id=session_id,
        members=members,
        topic=topic,
        user_name=user_name,
        twin_context=profile.get("twin_context") or "",
        client=client,
        model=model,
        top_k=_resolve_top_k(top_k),
        discussion_brief=merged_brief,
        user_avatar_url=profile.get("avatar_url") or "",
        user_id=profile.get("id"),
    )
    done = msg is None
    fresh = chat_store.list_messages(session_id)
    next_label = None if done else discussion.peek_next_turn_label(
        fresh, members, user_name
    )
    next_speaker = None if done else discussion.peek_next_speaker(
        fresh,
        members,
        user_name,
        user_avatar_url=profile.get("avatar_url") or "",
    )
    return {
        "done": done,
        "message": msg,
        "next_label": next_label,
        "next_speaker": next_speaker,
    }


def _turn_state(
    session_id: int,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    session = chat_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="找不到聊天室")
    members = session.get("members") or []
    profile = profile or chat_store.get_profile()
    user_name = profile.get("display_name") or "你"
    messages = chat_store.list_messages(session_id)
    next_label = discussion.peek_next_turn_label(messages, members, user_name)
    next_speaker = discussion.peek_next_speaker(
        messages,
        members,
        user_name,
        user_avatar_url=profile.get("avatar_url") or "",
    )
    return {
        "done": next_label is None,
        "next_label": next_label,
        "next_speaker": next_speaker,
        "message_count": len(messages),
    }


@app.get("/api/sessions/{session_id}/insights")
def api_session_insights(
    session_id: int,
    refresh: bool = Query(False),
    live: bool = Query(False, description="每則發言後即時重畫心智圖（規則版，不跑 LLM）"),
    max_messages: int | None = Query(
        None,
        ge=0,
        le=500,
        description="僅納入前 N 則訊息（思考中預覽，不含尚未顯示的回覆）",
    ),
    x_session_owner: str | None = Header(None, alias="X-Session-Owner"),
    user: dict[str, Any] = Depends(require_user),
):
    """依討論內容產生心智圖與意見差距曲線資料。"""
    _enforce_session_access(
        session_id,
        x_session_owner=x_session_owner,
        user=user,
    )
    session = chat_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="找不到聊天室")
    messages = chat_store.list_messages(session_id)
    if max_messages is not None:
        messages = messages[:max_messages]
    msg_count = len(chat_store.list_messages(session_id))
    if not refresh and not live:
        cached = discussion_insights.get_cached_insights(session_id, msg_count)
        if cached:
            return {
                "insights": cached,
                "message_count": msg_count,
                "cached": True,
                "persisted": True,
            }
        snap = discussion_insights.get_stored_insights_snapshot(session_id)
        if snap and snap["message_count"] < msg_count:
            stale = dict(snap["insights"])
            stale["stale"] = True
            stale["stored_message_count"] = snap["message_count"]
            return {
                "insights": stale,
                "message_count": msg_count,
                "cached": True,
                "persisted": True,
                "stale": True,
            }

    topic = session.get("topic") or session.get("title") or "討論"
    members = session.get("members") or []
    client = None
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    try:
        client, model = _discussion_client()
    except HTTPException:
        client = None

    try:
        insights = discussion_insights.build_session_insights(
            session_id=session_id,
            topic=topic,
            members=members,
            messages=messages,
            message_count=msg_count,
            client=client,
            model=model,
            force=refresh,
            live_only=live and not refresh,
        )
    except Exception as exc:
        _log.exception("session insights failed: %s", exc)
        insights = discussion_insights.build_session_insights(
            session_id=session_id,
            topic=topic,
            members=members,
            messages=messages,
            message_count=msg_count,
            client=None,
            force=False,
            live_only=True,
        )
        insights["update_label"] = "即時更新（分析暫時失敗，已改用規則版）"

    insights["message_count"] = msg_count
    discussion_insights.set_cached_insights(session_id, msg_count, insights)
    return {
        "insights": insights,
        "message_count": msg_count,
        "cached": False,
        "persisted": True,
        "live": live and not refresh,
        "update_mode": insights.get("update_mode") or "live",
    }


@app.get("/api/sessions/{session_id}/turn-state")
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


@app.post("/api/sessions/{session_id}/turn")
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


@app.post("/api/sessions/{session_id}/discuss")
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


@app.post("/api/sessions/{session_id}/messages")
def api_send_message(
    session_id: int,
    body: SendMessageRequest,
    x_session_owner: str | None = Header(None, alias="X-Session-Owner"),
    user: dict[str, Any] = Depends(require_user),
):
    """選填插話：有內容時會觸發新一輪辯論與結論。"""
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="插話內容不可為空")

    _enforce_session_access(
        session_id,
        x_session_owner=x_session_owner,
        user=user,
    )
    session = chat_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="找不到聊天室")

    guest_id = None

    requested_reply_to = (body.reply_to or "all").strip() or "all"
    profile = _profile_for_user(user)
    members = session.get("members") or []
    reply_to = requested_reply_to

    if requested_reply_to not in ("all", "user_twin"):
        by_slug: dict[str, dict[str, Any]] = {}
        by_name: dict[str, dict[str, Any]] = {}
        for m in members:
            slug = (m.get("person_slug") or m.get("slug") or "").strip()
            name = (m.get("name_zh") or "").strip()
            if slug:
                by_slug[slug] = m
            if name:
                by_name[name] = m
        if requested_reply_to not in by_slug:
            alias_hit = by_name.get(requested_reply_to)
            if alias_hit:
                reply_to = (alias_hit.get("person_slug") or alias_hit.get("slug") or "").strip() or "all"
            elif members:
                fallback_slug = (
                    members[0].get("person_slug")
                    or members[0].get("slug")
                    or "all"
                )
                reply_to = str(fallback_slug).strip() or "all"
                _log.warning(
                    "session %s reply target '%s' not found; fallback to '%s'",
                    session_id,
                    requested_reply_to,
                    reply_to,
                )
            else:
                reply_to = "all"

    meta: dict[str, str] = {
        "reply_to": reply_to,
        "requested_reply_to": requested_reply_to,
    }

    user_msg = chat_store.add_message(
        session_id, "user", content, guest_id=guest_id, sources=meta
    )
    user_msg["reply_to"] = reply_to
    user_msg["requested_reply_to"] = requested_reply_to
    topic = session.get("topic") or session.get("title") or "討論"
    replies: list[dict[str, Any]] = []
    speaking_order: list[dict[str, Any]] = []
    follow_up: str | None = None
    follow_up_error: str | None = None

    # 凡能進入討論室插話者，皆可觸發名人回覆（不限房主）
    can_run = bool(members)

    target_member: dict[str, Any] | None = None
    target_slug = reply_to
    if can_run and reply_to not in ("all", "user_twin"):
        for m in members:
            m_slug = (m.get("person_slug") or m.get("slug") or "").strip()
            if m_slug == reply_to:
                target_member = m
                target_slug = m_slug
                break
        if not target_member and members:
            target_member = members[0]
            target_slug = (
                (target_member.get("person_slug") or target_member.get("slug") or "").strip()
                or "all"
            )
            reply_to = target_slug

    def _fallback_direct_reply() -> dict[str, Any] | None:
        if target_slug in ("all", "user_twin"):
            return None
        member = target_member
        if not member:
            return None
        name_zh = member.get("name_zh") or target_slug
        user_text = (content or "").strip()
        fallback_text = ""
        if llm_client:
            try:
                quick_system = (
                    f"你是{name_zh}。請直接回覆使用者問題，語氣自然、具體，"
                    "使用繁體中文，2-4 句，不要用『我會先回答你』這種前言。"
                )
                quick_user = (
                    f"討論主題：{topic}\n"
                    f"使用者剛剛問：{user_text or '（未提供）'}\n"
                    "請直接給出你的觀點與一個具體建議。"
                )
                resp = llm_client.chat.completions.create(
                    model=llm_model,
                    messages=[
                        {"role": "system", "content": quick_system},
                        {"role": "user", "content": quick_user},
                    ],
                    temperature=0.55,
                    max_tokens=220,
                )
                fallback_text = (resp.choices[0].message.content or "").strip()
            except Exception:
                fallback_text = ""
        if not fallback_text:
            if user_text:
                fallback_text = (
                    f"你提到「{user_text}」這點很關鍵。以「{topic}」來看，"
                    f"{name_zh} 的建議是先把問題拆成可量化指標，先做一個小型驗證，"
                    "再依結果決定是否全面推進。"
                )
            else:
                fallback_text = (
                    f"針對「{topic}」，我建議先聚焦在最能影響決策品質的核心指標，"
                    "用小步快跑的方式驗證，再逐步擴大。"
                )
        packed = {
            "sources": [],
            "segments": [],
            "phase": "debate",
            "direct_reply": True,
            "reply_to": target_slug,
        }
        msg = chat_store.add_message(
            session_id,
            target_slug,
            fallback_text,
            person_slug=target_slug,
            sources=packed,
            phase="debate",
            content_segments=[],
        )
        return {
            **msg,
            "person_slug": target_slug,
            "person_name_zh": name_zh,
            "avatar_url": member.get("avatar_url") or "",
            "phase": "debate",
            "sources": [],
            "content_segments": [],
            "direct_reply": True,
            "reply_to": target_slug,
        }

    llm_client = None
    llm_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    single_follow_up_timeout_sec = float(
        os.getenv("CHAT_SINGLE_FOLLOW_UP_TIMEOUT_SEC", "8")
    )
    round_follow_up_timeout_sec = float(
        os.getenv("CHAT_ROUND_FOLLOW_UP_TIMEOUT_SEC", "120")
    )
    round_member_timeout_sec = float(
        os.getenv("CHAT_ROUND_MEMBER_TIMEOUT_SEC", "12")
    )
    round_soft_timeout_sec = float(
        os.getenv("CHAT_ROUND_SOFT_TIMEOUT_SEC", "45")
    )
    if can_run:
        try:
            llm_client, llm_model = _discussion_client()
            merged_brief = (session.get("context_brief") or "").strip() or None
            common = dict(
                session_id=session_id,
                members=members,
                topic=topic,
                user_name=profile.get("display_name") or "你",
                twin_context=profile.get("twin_context") or "",
                client=llm_client,
                model=llm_model,
                top_k=_resolve_top_k(body.top_k),
                discussion_brief=merged_brief,
                user_avatar_url=profile.get("avatar_url") or "",
                user_id=profile.get("id"),
            )
            if reply_to == "all":
                ordered_members = [
                    m
                    for m in members
                    if (m.get("person_slug") or m.get("slug") or "").strip()
                ]
                random.shuffle(ordered_members)
                round_started = time.monotonic()
                for m in ordered_members:
                    slug = (m.get("person_slug") or m.get("slug") or "").strip()
                    if not slug:
                        continue
                    speaking_order.append(
                        {
                            "person_slug": slug,
                            "name_zh": m.get("name_zh") or slug,
                            "avatar_url": m.get("avatar_url") or "",
                            "kind": "celeb",
                            "topic_fit_score": m.get("topic_fit_score"),
                        }
                    )
                    elapsed = time.monotonic() - round_started
                    if replies and elapsed >= round_soft_timeout_sec:
                        break
                    remaining = round_follow_up_timeout_sec - elapsed
                    if remaining <= 1:
                        break
                    one_timeout = max(1.0, min(round_member_timeout_sec, remaining))
                    try:
                        fut = _RECOMMEND_POOL.submit(
                            discussion.run_direct_reply,
                            **common,
                            target=slug,
                        )
                        one = fut.result(timeout=one_timeout)
                        if one:
                            one["interjection_index"] = len(replies) + 1
                            replies.append(one)
                    except FuturesTimeout:
                        _log.warning(
                            "session %s member %s interjection timed out after %.1fs",
                            session_id,
                            slug,
                            one_timeout,
                        )
                        continue
                    except Exception as exc:
                        _log.warning(
                            "session %s member %s interjection failed: %s",
                            session_id,
                            slug,
                            exc,
                        )
                        continue
                total = len(replies)
                for msg in replies:
                    msg["interjection_total"] = total
                if not replies:
                    follow_up_error = "本輪名人回覆逾時，請再試一次"
                follow_up = "round"
            else:
                fut = _RECOMMEND_POOL.submit(
                    discussion.run_direct_reply,
                    **common,
                    target=target_slug,
                )
                one = fut.result(timeout=single_follow_up_timeout_sec)
                if one:
                    replies.append(one)
                else:
                    fb = _fallback_direct_reply()
                    if fb:
                        replies.append(fb)
                follow_up = "single"
        except FuturesTimeout:
            timeout_used = (
                round_follow_up_timeout_sec if reply_to == "all" else single_follow_up_timeout_sec
            )
            follow_up_error = f"名人回覆逾時（>{int(timeout_used)} 秒）"
            if reply_to not in ("all", "user_twin"):
                fb = _fallback_direct_reply()
                if fb:
                    replies.append(fb)
                    follow_up_error = None
                    follow_up = "single"
        except HTTPException as exc:
            if exc.status_code not in (503, 500):
                raise
            follow_up_error = str(exc.detail)
            if reply_to not in ("all", "user_twin"):
                fb = _fallback_direct_reply()
                if fb:
                    replies.append(fb)
                    follow_up_error = None
                    follow_up = "single"
        except Exception as exc:
            follow_up_error = str(exc)
            if reply_to not in ("all", "user_twin"):
                fb = _fallback_direct_reply()
                if fb:
                    replies.append(fb)
                    follow_up_error = None
                    follow_up = "single"

    # 圖譜由前端在「思考中」以 live=1 更新；插話批次完成後不在此強制 LLM 覆寫
    insights_payload: dict[str, Any] | None = None

    try:
        state = _turn_state(session_id, profile=profile)
        result = {
            "user_message": user_msg,
            "content": content,
            "reply_to": reply_to,
            "requested_reply_to": requested_reply_to,
            "replies": replies,
            "speaking_order": speaking_order if reply_to == "all" else [],
            "follow_up": follow_up,
            "follow_up_error": follow_up_error,
            "insights": insights_payload,
            "awaiting_turn": not state["done"],
            "next_label": state["next_label"],
            "guest_id": guest_id,
        }
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/query")
def api_query(body: QueryRequest):
    question = body.question.strip()
    person = body.person.strip()
    source_types = (
        [t.strip() for t in body.types.split(",") if t.strip()]
        if body.types.strip()
        else None
    )
    if not question or not person:
        raise HTTPException(status_code=400, detail="請提供 question 與 person")
    try:
        results = search_chunks(
            question,
            person_slug=person,
            top_k=_resolve_top_k(body.top_k),
            source_types=source_types,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {
        "question": question,
        "person": person,
        "results": [
            {
                "chunk_id": r["chunk_id"],
                "similarity": round(float(r["similarity"]), 4),
                "source_type": r["source_type"],
                "title": r["title"],
                "source_url": r["source_url"],
                "content": r["content"],
            }
            for r in results
        ],
        "context": format_context(results),
    }
