"""
批次抓取名人頭像（維基百科公開 API）→ 存本機 + 寫入 persons.avatar_url

維基條目通常有 portrait，適合 40 位公眾人物；少數可能需手動補。

執行：
  cd ~/Desktop/digital_twin_project
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy
  ./venv/bin/python crawl/fetch_avatars.py
  ./venv/bin/python crawl/fetch_avatars.py --dry-run
  ./venv/bin/python crawl/fetch_avatars.py --slug elon_musk
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote

import psycopg2
import requests
from psycopg2.extras import RealDictCursor

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "rag"))

from config import DB_CONFIG  # noqa: E402

AVATAR_DIR = PROJECT_ROOT / "web" / "static" / "avatars"
HEADERS = {
    "User-Agent": "digital-twin-fenshen-youshu/1.0 (thesis; local)",
}
THUMB_SIZE = 400

# slug → (lang, 維基頁面標題)；標題錯誤時可手動覆寫
WIKI_OVERRIDES: dict[str, tuple[str, str]] = {
    "elon_musk": ("en", "Elon Musk"),
    "jensen_huang": ("en", "Jensen Huang"),
    "steve_jobs": ("en", "Steve Jobs"),
    "bill_gates": ("en", "Bill Gates"),
    "sam_altman": ("en", "Sam Altman"),
    "mark_zuckerberg": ("en", "Mark Zuckerberg"),
    "confucius": ("zh", "孔子"),
    "sun_tzu": ("zh", "孙子"),
    "ken_robinson": ("en", "Ken Robinson"),
}


def _session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    s.headers.update(HEADERS)
    return s


def _wiki_pageimage_thumb(sess: requests.Session, lang: str, title: str) -> str | None:
    wiki_title = title.strip().replace(" ", "_")
    try:
        resp = sess.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": wiki_title,
                "prop": "pageimages",
                "format": "json",
                "pithumbsize": THUMB_SIZE,
            },
            timeout=20,
        )
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            if int(page.get("pageid", -1)) < 0:
                continue
            thumb = page.get("thumbnail") or {}
            if thumb.get("source"):
                return thumb["source"]
    except requests.RequestException:
        pass
    return None


def _wiki_summary_thumb(sess: requests.Session, lang: str, title: str) -> str | None:
    candidates = [
        title.strip().replace(" ", "_"),
        title.strip(),
        quote(title.strip().replace(" ", "_"), safe=""),
    ]
    seen: set[str] = set()
    for cand in candidates:
        if not cand or cand in seen:
            continue
        seen.add(cand)
        url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{cand}"
        try:
            resp = sess.get(url, timeout=20)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            thumb = (resp.json().get("thumbnail") or {}).get("source")
            if thumb:
                return thumb
        except requests.RequestException:
            continue
    return _wiki_pageimage_thumb(sess, lang, title)


def _wiki_search_title(sess: requests.Session, lang: str, query: str) -> str | None:
    try:
        resp = sess.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={
                "action": "opensearch",
                "search": query,
                "limit": 1,
                "namespace": 0,
                "format": "json",
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        if len(data) >= 2 and data[1]:
            return data[1][0]
    except requests.RequestException:
        pass
    return None


def resolve_thumbnail(sess: requests.Session, slug: str, name_en: str, name_zh: str) -> tuple[str | None, str | None]:
    """回傳 (thumb_url, source_label)"""
    if slug in WIKI_OVERRIDES:
        lang, title = WIKI_OVERRIDES[slug]
        url = _wiki_summary_thumb(sess, lang, title)
        if url:
            return url, f"wikipedia_{lang}"

    for lang, title in [("en", name_en), ("zh", name_zh)]:
        if not title or not str(title).strip():
            continue
        url = _wiki_summary_thumb(sess, lang, str(title).strip())
        if url:
            return url, f"wikipedia_{lang}"

    for lang, query in [("en", name_en), ("zh", name_zh)]:
        if not query:
            continue
        found = _wiki_search_title(sess, lang, str(query).strip())
        if found:
            url = _wiki_summary_thumb(sess, lang, found)
            if url:
                return url, f"wikipedia_{lang}_search"
    return None, None


def download_image(sess: requests.Session, url: str, dest: Path) -> bool:
    try:
        resp = sess.get(url, timeout=30)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return True
    except requests.RequestException:
        return False


def ensure_schema(cur) -> None:
    cur.execute("ALTER TABLE persons ADD COLUMN IF NOT EXISTS avatar_url TEXT;")
    cur.execute("ALTER TABLE persons ADD COLUMN IF NOT EXISTS avatar_source TEXT;")


def process_person(
    sess: requests.Session,
    person: dict,
    *,
    dry_run: bool,
) -> tuple[str, str] | None:
    slug = person["slug"]
    name_en = person.get("name_en") or ""
    name_zh = person.get("name_zh") or ""

    thumb_url, source = resolve_thumbnail(sess, slug, name_en, name_zh)
    if not thumb_url:
        print(f"  ✗ {slug} ({name_zh}) — 維基找不到頭像")
        return None

    ext = ".jpg"
    if ".png" in thumb_url.lower():
        ext = ".png"
    local_name = f"{slug}{ext}"
    local_path = AVATAR_DIR / local_name
    public_url = f"/static/avatars/{local_name}"

    print(f"  ✓ {slug} ← {source}")
    if dry_run:
        print(f"      {thumb_url[:80]}…")
        return public_url, source

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    if not download_image(sess, thumb_url, local_path):
        print(f"      下載失敗，僅存遠端 URL")
        public_url = thumb_url

    return public_url, source


def main() -> None:
    parser = argparse.ArgumentParser(description="從維基抓取名人頭像")
    parser.add_argument("--dry-run", action="store_true", help="只查不寫入")
    parser.add_argument("--slug", help="只處理一位")
    parser.add_argument("--delay", type=float, default=0.35, help="請求間隔秒數")
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_CONFIG)
    sess = _session()
    ok = fail = 0

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            ensure_schema(cur)
            conn.commit()

            if args.slug:
                cur.execute(
                    "SELECT id, slug, name_en, name_zh, avatar_source "
                    "FROM persons WHERE slug = %s;",
                    (args.slug,),
                )
            else:
                cur.execute(
                    "SELECT id, slug, name_en, name_zh, avatar_source "
                    "FROM persons ORDER BY name_zh;"
                )
            rows = cur.fetchall()

        print(f"共 {len(rows)} 位名人\n")

        for person in rows:
            if person.get("avatar_source") == "ai-generated-illustration":
                print(f"略過 {person['slug']}：保留專案內的 AI 生成頭像")
                continue
            result = process_person(sess, dict(person), dry_run=args.dry_run)
            if not result:
                fail += 1
            else:
                ok += 1
                if not args.dry_run:
                    public_url, source = result
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            UPDATE persons
                            SET avatar_url = %s, avatar_source = %s, updated_at = NOW()
                            WHERE slug = %s;
                            """,
                            (public_url, source, person["slug"]),
                        )
                    conn.commit()
            time.sleep(args.delay)

    finally:
        conn.close()

    print(f"\n完成：成功 {ok}，失敗 {fail}")
    if not args.dry_run:
        print(f"頭像目錄：{AVATAR_DIR}")


if __name__ == "__main__":
    main()
