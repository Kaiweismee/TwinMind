"""網頁入口：首頁與實驗室頁面。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from web.core.settings import STATIC


router = APIRouter()


@router.get("/")
def home():
    return FileResponse(STATIC / "index.html")


@router.get("/lab")
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
