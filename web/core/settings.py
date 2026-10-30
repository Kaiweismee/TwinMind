"""網頁路徑與環境設定；在載入功能模組之前讀取專案根目錄的 .env。"""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

STATIC = ROOT / "web" / "static"
PROFILE_AVATAR_ROOT = ROOT / "data" / "profile_avatars"
AUTH_COOKIE = "dt_auth"
AUTH_COOKIE_MAX_AGE = int(os.getenv("AUTH_SESSION_DAYS", "30")) * 86400
AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "").lower() in ("1", "true", "yes")
MAX_PROFILE_AVATAR_BYTES = int(os.getenv("PROFILE_AVATAR_MAX_BYTES", str(4 * 1024 * 1024)))
RECOMMEND_TIMEOUT_SEC = float(os.getenv("TOPIC_FIT_RECOMMEND_TIMEOUT", "75"))
