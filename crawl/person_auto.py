"""
新增名人：輸入姓名與資訊 → 自動寫入 persons + 爬蟲（唯一入口）

預設會用 yt-dlp 搜尋並抓取相關 YouTube 字幕（不需手動找 video_id）。

互動：
  ./venv/bin/python crawl/person_auto.py

命令列：
  ./venv/bin/python crawl/person_auto.py \\
    --name-zh "山姆·阿特曼" --name-en "Sam Altman" --company "OpenAI"

只補抓 YouTube（已存在的人）：
  ./venv/bin/python crawl/person_auto.py --only-youtube --slug sam_altman \\
    --name-en "Sam Altman"

完成後：
  ./venv/bin/python rag/embed_chunks.py --no-index
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import psycopg2
import requests
from psycopg2.extras import RealDictCursor

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "rag"))

from db_utils import DB_CONFIG, get_person_id, print_stats, save_document_and_chunks
from interview_fetch import MIN_INTERVIEW_CHARS, build_interview_content
from news_rss import REQUEST_DELAY_SEC as NEWS_DELAY
from news_rss import build_raw_content, fetch_feed, google_news_rss_url, strip_html
from speech_fetch import (
    REQUEST_DELAY_SEC as SPEECH_DELAY,
    YouTubeSpeech,
    fetch_youtube_transcript,
)
from wikipedia_more import fetch_wiki_full_text
from youtube_discover import discover_videos, merge_video_lists

HEADERS = {
    "User-Agent": "digital-twin-thesis-poc/1.0 (education; contact: local-dev)",
}

MAX_NEWS_PER_QUERY = 20
NEWS_LANG_CONFIG = {
    "zh": ("zh-TW", "TW", "TW:zh-Hant"),
    "en": ("en-US", "US", "US:en"),
}


def make_slug(name_en: str) -> str:
    s = name_en.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_") or "person"


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def wiki_search_title(lang: str, query: str) -> str | None:
    api = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "opensearch",
        "search": query,
        "limit": 1,
        "format": "json",
    }
    try:
        with requests.Session() as session:
            session.trust_env = False
            resp = session.get(api, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if len(data) >= 2 and data[1]:
            return data[1][0]
    except requests.RequestException as e:
        print(f"  維基搜尋失敗 ({lang} {query})：{e}")
    return None


def insert_person(slug: str, name_zh: str, name_en: str, company: str = "") -> None:
    bio = f"{name_en} 公開資料，用於數位分身 RAG。"
    if company:
        bio = f"{name_en}（{company}）公開演講、新聞與訪談資料，用於數位分身 RAG。"
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO persons (slug, name_zh, name_en, bio) VALUES (%s, %s, %s, %s)
                ON CONFLICT (slug) DO UPDATE SET
                    name_zh = EXCLUDED.name_zh,
                    name_en = EXCLUDED.name_en,
                    bio = EXCLUDED.bio,
                    updated_at = NOW();
                """,
                (slug, name_zh, name_en, bio),
            )
        conn.commit()
    finally:
        conn.close()


def _save_wiki_page(
    cur, conn, person_id: int, lang: str, title: str
) -> tuple[bool, str]:
    result = fetch_wiki_full_text(lang, title)
    time.sleep(1.0)
    if not result:
        return False, title
    extract, source_url, resolved = result
    doc_id, n_chunks = save_document_and_chunks(
        cur,
        person_id=person_id,
        source_url=source_url,
        title=resolved,
        raw_content=extract,
        language=lang,
        source_type="wiki",
        metadata={"source": "wikipedia_auto", "wiki_title": title},
    )
    conn.commit()
    print(f"  維基 ✓ [{doc_id}] {resolved} ({n_chunks} chunks)")
    return True, resolved


def crawl_wikipedia(
    person_slug: str,
    name_zh: str,
    name_en: str,
    extra_pages: list[tuple[str, str]],
) -> tuple[int, int]:
    ok, skip = 0, 0
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            person_id = get_person_id(cur, person_slug)
            candidates: list[tuple[str, str]] = list(extra_pages)

            for lang, q in (("zh", name_zh), ("en", name_en)):
                title = wiki_search_title(lang, q)
                if title:
                    candidates.append((lang, title))
                time.sleep(0.5)

            seen: set[tuple[str, str]] = set()
            for lang, title in candidates:
                key = (lang, title)
                if key in seen:
                    continue
                seen.add(key)

                success, label = _save_wiki_page(cur, conn, person_id, lang, title)
                if success:
                    ok += 1
                else:
                    print(f"  維基跳過：({lang}) {label}")
                    skip += 1
    finally:
        conn.close()
    return ok, skip


def _news_queries(
    name_zh: str, name_en: str, company: str, extra: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    qs: list[tuple[str, str]] = [
        (name_zh, "zh"),
        (f"{name_zh} 專訪", "zh"),
        (f"{name_zh} 演講", "zh"),
        (name_en, "en"),
        (f"{name_en} interview", "en"),
        (f"{name_en} keynote", "en"),
    ]
    if company:
        qs.extend(
            [
                (f"{name_zh} {company}", "zh"),
                (f"{name_en} {company}", "en"),
            ]
        )
    qs.extend(extra)
    # 去重，保留順序
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in qs:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def crawl_google_news(
    person_slug: str, queries: list[tuple[str, str]], source_type: str
) -> tuple[int, int, int]:
    ok, skip, fail = 0, 0, 0
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            person_id = get_person_id(cur, person_slug)
            for query, lang in queries:
                hl, gl, ceid = NEWS_LANG_CONFIG[lang]
                url = google_news_rss_url(query, hl, gl, ceid)
                print(f"  RSS [{source_type}]：{query}")
                try:
                    feed = fetch_feed(url)
                    time.sleep(NEWS_DELAY)
                except Exception as e:
                    print(f"    ✗ {e}")
                    fail += 1
                    continue

                for entry in feed.entries[:MAX_NEWS_PER_QUERY]:
                    title = strip_html(entry.get("title", ""))
                    link = (entry.get("link") or "").strip()
                    if not title or not link:
                        skip += 1
                        continue
                    summary = strip_html(
                        entry.get("summary") or entry.get("description") or ""
                    )
                    published = entry.get("published", "")
                    source_name = ""
                    if entry.get("source") and entry.source.get("title"):
                        source_name = entry.source["title"]
                    if source_type == "interview":
                        raw = build_interview_content(
                            title, summary, published, source_name, query
                        )
                        min_len = MIN_INTERVIEW_CHARS
                    else:
                        raw = build_raw_content(
                            title, summary, published, source_name
                        )
                        min_len = 30
                    if len(raw) < min_len:
                        skip += 1
                        continue
                    try:
                        save_document_and_chunks(
                            cur,
                            person_id=person_id,
                            source_url=link,
                            title=title,
                            raw_content=raw,
                            language=lang,
                            source_type=source_type,
                            metadata={
                                "source": f"google_news_rss_{source_type}",
                                "query": query,
                            },
                        )
                        conn.commit()
                        ok += 1
                    except Exception:
                        conn.rollback()
                        fail += 1
    finally:
        conn.close()
    return ok, skip, fail


def parse_youtube_list(spec: str) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    if not spec.strip():
        return items
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            vid, title = part.split(":", 1)
        else:
            vid, title = part, f"YouTube {part}"
        items.append((vid.strip(), title.strip()))
    return items


def parse_extra_queries(spec: str) -> list[tuple[str, str]]:
    """逗號分隔；含中文→zh，否則 en"""
    out: list[tuple[str, str]] = []
    for part in spec.split(","):
        q = part.strip()
        if not q:
            continue
        lang = "zh" if _has_cjk(q) else "en"
        out.append((q, lang))
    return out


def parse_wiki_pages(spec: str) -> list[tuple[str, str]]:
    """格式：zh:比爾·盖茨,en:Bill_Gates"""
    pages: list[tuple[str, str]] = []
    for part in spec.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        lang, title = part.split(":", 1)
        lang = lang.strip().lower()
        title = title.strip()
        if lang in ("zh", "en") and title:
            pages.append((lang, title))
    return pages


def crawl_youtube_speeches(
    person_slug: str, videos: list[tuple[str, str]], source_type: str
) -> tuple[int, int]:
    ok, skip = 0, 0
    if not videos:
        return ok, skip

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            person_id = get_person_id(cur, person_slug)
            for video_id, title in videos:
                print(f"  YouTube：{title}")
                speech = YouTubeSpeech(person_slug, video_id, title, "en")
                text, method = fetch_youtube_transcript(speech)
                time.sleep(SPEECH_DELAY)
                if not text or len(text) < 500:
                    print("    → 跳過（無字幕或太短）")
                    skip += 1
                    continue
                doc_id, n_chunks = save_document_and_chunks(
                    cur,
                    person_id=person_id,
                    source_url=f"https://www.youtube.com/watch?v={video_id}",
                    title=title,
                    raw_content=text,
                    language="en",
                    source_type=source_type,
                    metadata={"source": method, "video_id": video_id},
                )
                conn.commit()
                ok += 1
                print(f"    ✓ [{doc_id}] {len(text)} 字, {n_chunks} chunks")
    finally:
        conn.close()
    return ok, skip


def lookup_person(slug: str) -> tuple[str, str]:
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT name_zh, name_en FROM persons WHERE slug = %s;",
                (slug,),
            )
            row = cur.fetchone()
            if not row:
                raise SystemExit(f"找不到 persons.slug = `{slug}`，請先新增此人。")
            return row[0] or "", row[1] or ""
    finally:
        conn.close()


def resolve_youtube_videos(
    name_en: str,
    name_zh: str,
    company: str,
    youtube_spec: str,
    *,
    auto: bool,
    max_total: int,
) -> list[tuple[str, str]]:
    manual = parse_youtube_list(youtube_spec)
    if not auto:
        return manual
    print(f"  自動搜尋 YouTube（最多 {max_total} 支）…")
    auto_list = discover_videos(
        name_en,
        name_zh=name_zh,
        company=company,
        max_total=max_total,
    )
    merged = merge_video_lists(manual, auto_list)
    if not merged:
        print("  （搜尋無結果；可改用 --youtube 手動指定 video_id）")
    return merged


def prompt_if_missing(value: str, label: str, *, optional: bool = False) -> str:
    if value.strip():
        return value.strip()
    hint = "（可 Enter 跳過）" if optional else ""
    return input(f"{label}{hint}：").strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="輸入名人資訊，自動建庫並爬蟲（不需另建腳本）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--name-zh", help="中文名")
    parser.add_argument("--name-en", help="英文名")
    parser.add_argument("--slug", help="資料庫 slug（預設由英文名自動產生）")
    parser.add_argument("--company", help="公司/領域關鍵字，例如 Apple、Microsoft")
    parser.add_argument(
        "--youtube",
        help="YouTube：video_id:標題，多個用逗號分隔",
    )
    parser.add_argument(
        "--extra-queries",
        help="額外 Google News 關鍵字，逗號分隔（自動判斷中/英）",
    )
    parser.add_argument(
        "--wiki-pages",
        help="額外維基頁，格式 zh:標題,en:Title",
    )
    parser.add_argument("--skip-embed-hint", action="store_true")
    parser.add_argument(
        "--only-youtube",
        action="store_true",
        help="只抓 YouTube 字幕（需 --slug；預設自動搜尋）",
    )
    parser.add_argument(
        "--no-auto-youtube",
        action="store_true",
        help="不自動搜尋 YouTube（僅使用 --youtube 手動清單）",
    )
    parser.add_argument(
        "--youtube-max",
        type=int,
        default=8,
        help="自動搜尋時最多嘗試幾支影片（預設 8）",
    )
    args = parser.parse_args()

    if args.only_youtube:
        slug = (args.slug or "").strip()
        if not slug:
            raise SystemExit("只抓 YouTube 時請加上 --slug，例如：--slug sam_altman")
        name_zh = (args.name_zh or "").strip()
        name_en = (args.name_en or "").strip()
        company = (args.company or "").strip()
        if not name_en and not name_zh:
            name_zh, name_en = lookup_person(slug)
        youtube_spec = (args.youtube or "").strip()
        auto_yt = not args.no_auto_youtube
        if not auto_yt and not youtube_spec:
            raise SystemExit("請提供 --youtube，或拿掉 --no-auto-youtube 以自動搜尋")
        print(f"=== 只抓 YouTube：{slug} ===\n")
        videos = resolve_youtube_videos(
            name_en,
            name_zh,
            company,
            youtube_spec,
            auto=auto_yt,
            max_total=args.youtube_max,
        )
        y_ok, y_skip = crawl_youtube_speeches(slug, videos, "speech")
        print(f"\n完成：成功 {y_ok}，跳過 {y_skip}")
        if not args.skip_embed_hint:
            print("\n下一步：")
            print("  ./venv/bin/python rag/embed_chunks.py --no-index")
        return

    print("=== 數位分身：新增名人並爬蟲 ===")
    print("（只需執行本程式，不必建立 crawl_xxx.py）\n")

    name_zh = prompt_if_missing(args.name_zh or "", "中文名")
    name_en = prompt_if_missing(args.name_en or "", "英文名")
    company = (args.company or "").strip()
    if not company and not (args.name_zh and args.name_en):
        company = prompt_if_missing("", "公司/關鍵字", optional=True)

    slug = (args.slug or "").strip() or make_slug(name_en)
    if not (args.slug or "").strip() and not (args.name_zh and args.name_en):
        custom = input(f"slug（Enter 使用 `{slug}`）：").strip()
        if custom:
            slug = custom

    auto_yt = not args.no_auto_youtube
    youtube_spec = args.youtube
    if youtube_spec is None and not (args.name_zh and args.name_en):
        if args.no_auto_youtube:
            youtube_spec = prompt_if_missing(
                "", "YouTube video_id:標題（多個逗號分隔）", optional=True
            )
        else:
            youtube_spec = prompt_if_missing(
                "",
                "YouTube video_id:標題（可 Enter 跳過，將自動搜尋）",
                optional=True,
            )
    youtube_spec = youtube_spec or ""

    extra_q_spec = args.extra_queries or ""
    wiki_spec = args.wiki_pages or ""

    print(f"\nslug：{slug}")
    print(f"中文：{name_zh}｜英文：{name_en}")
    if company:
        print(f"關鍵字：{company}")

    extra_news = parse_extra_queries(extra_q_spec)
    extra_wiki = parse_wiki_pages(wiki_spec)

    print("\n1. 寫入 persons …")
    insert_person(slug, name_zh, name_en, company)

    print("\n2. 維基百科 …")
    w_ok, w_skip = crawl_wikipedia(slug, name_zh, name_en, extra_wiki)
    print(f"   維基：成功 {w_ok}，跳過 {w_skip}")

    news_queries = _news_queries(name_zh, name_en, company, extra_news)
    interview_queries = [
        (f"{name_zh} 專訪", "zh"),
        (f"{name_zh} 訪談", "zh"),
        (f"{name_en} interview", "en"),
        (f"{name_en} exclusive interview", "en"),
    ]

    print("\n3. 新聞 RSS …")
    n_ok, n_skip, n_fail = crawl_google_news(slug, news_queries, "news")
    print(f"   新聞：成功 {n_ok}，跳過 {n_skip}，失敗 {n_fail}")

    print("\n4. 訪談 RSS …")
    i_ok, i_skip, i_fail = crawl_google_news(slug, interview_queries, "interview")
    print(f"   訪談：成功 {i_ok}，跳過 {i_skip}，失敗 {i_fail}")

    print("\n5. YouTube 字幕 …")
    videos = resolve_youtube_videos(
        name_en,
        name_zh,
        company,
        youtube_spec,
        auto=auto_yt,
        max_total=args.youtube_max,
    )
    y_ok, y_skip = crawl_youtube_speeches(slug, videos, "speech")
    if videos:
        print(f"   YouTube：成功 {y_ok}，跳過 {y_skip}")
    elif auto_yt:
        print("   （自動搜尋無結果且未手動指定）")
    else:
        print("   （未提供 YouTube，已跳過）")

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        print("\n--- 統計 ---")
        print_stats(conn)
    finally:
        conn.close()

    print(f"\n✓ 完成。slug = `{slug}`")
    if not args.skip_embed_hint:
        print("\n下一步：")
        print("  ./venv/bin/python rag/embed_chunks.py --no-index")
        print(
            f'  ./venv/bin/python rag/query.py "你的問題" --person {slug}'
        )


if __name__ == "__main__":
    main()
