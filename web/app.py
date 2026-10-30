"""應用程式入口：組裝設定、靜態檔案、啟動工作與各功能 API。

啟動：./venv/bin/uvicorn web.app:app --reload --host 127.0.0.1 --port 8000
閱讀順序與功能對照請看 docs/ARCHITECTURE.md。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from web.core.settings import STATIC
from web.core.lifecycle import startup
from web.routers import (
    auth, discussion, insights, media, notifications, pages, person_chat,
    persons, profile, query, sessions, twin_chat, twins,
)

app = FastAPI(title="數位分身", version="2.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
app.on_event("startup")(startup)

# 各模組只宣告自己的路由；統一由入口註冊。
# sessions 內固定路徑 all-ids、join、preview 必須維持在動態 id 路由之前。
for router in (
    pages.router, auth.router, twins.router, twin_chat.router,
    person_chat.router, media.router, profile.router, persons.router,
    notifications.router, sessions.router, insights.router,
    discussion.router, query.router,
):
    app.include_router(router)
