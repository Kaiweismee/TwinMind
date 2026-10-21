"""
訪談爬蟲：Google News（訪談關鍵字）+ YouTube 字幕 + 網頁全文

寫入 documents，source_type = 'interview'

執行：
  cd ~/Desktop/digital_twin_project
  ./venv/bin/python crawl/interview_fetch.py
"""

from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from urllib.parse import quote_plus

import feedparser
import psycopg2
import requests
from psycopg2.extras import RealDictCursor

sys.path.insert(0, str(Path(__file__).parent))
from db_utils import DB_CONFIG, get_person_id, print_stats, save_document_and_chunks
from speech_fetch import (
    MIN_SPEECH_CHARS,
    REQUEST_DELAY_SEC,
    WebSpeech,
    YouTubeSpeech,
    fetch_web_article,
    fetch_youtube_transcript,
    print_stats_by_type,
)

HEADERS = {
    "User-Agent": "digital-twin-thesis-poc/1.0 (education; contact: local-dev)",
}

MAX_PER_FEED = 20
MIN_INTERVIEW_CHARS = 80


@dataclass
class InterviewNewsFeed:
    person_slug: str
    query: str
    language: str
    hl: str
    gl: str
    ceid: str


# --- Google News：專搜「訪談 / 專訪 / interview」---
INTERVIEW_NEWS_FEEDS = [
    InterviewNewsFeed("elon_musk", "馬斯克 專訪", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    InterviewNewsFeed("elon_musk", "馬斯克 訪談", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    InterviewNewsFeed("elon_musk", "Elon Musk interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("elon_musk", "Elon Musk exclusive interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("jensen_huang", "黃仁勳 專訪", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    InterviewNewsFeed("jensen_huang", "黃仁勳 訪談", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    InterviewNewsFeed("jensen_huang", "Jensen Huang interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("jensen_huang", "Jensen Huang CNBC interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("steve_jobs", "賈伯斯 專訪", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    InterviewNewsFeed("steve_jobs", "賈伯斯 訪談", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    InterviewNewsFeed("steve_jobs", "Steve Jobs interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("steve_jobs", "Steve Jobs 1995 interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("bill_gates", "蓋茲 專訪", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    InterviewNewsFeed("bill_gates", "蓋茲 訪談", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    InterviewNewsFeed("bill_gates", "Bill Gates interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("bill_gates", "Bill Gates 60 Minutes interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("andrew_ng", "吳恩達 專訪", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    InterviewNewsFeed("andrew_ng", "吳恩達 訪談", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    InterviewNewsFeed("andrew_ng", "Andrew Ng interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("andrew_ng", "Andrew Ng podcast", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("jeff_bezos", "Jeff Bezos interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("ray_dalio", "Ray Dalio interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("morris_chang", "張忠謀 專訪", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    InterviewNewsFeed("morris_chang", "Morris Chang interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("charlie_munger", "Charlie Munger interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("peter_thiel", "Peter Thiel interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("indra_nooyi", "Indra Nooyi interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("michael_porter", "Michael Porter interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("sheryl_sandberg", "Sheryl Sandberg interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("terry_gou", "郭台銘 專訪", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    InterviewNewsFeed("terry_gou", "Terry Gou interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("confucius", "孔子 教育思想", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    InterviewNewsFeed("peter_drucker", "Peter Drucker interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("ken_robinson", "Ken Robinson interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("sal_khan", "Sal Khan interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("john_dewey", "John Dewey philosophy education", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("maria_montessori", "Maria Montessori biography interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("sugata_mitra", "Sugata Mitra interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("carol_dweck", "Carol Dweck interview mindset", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("howard_gardner", "Howard Gardner interview", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("paulo_freire", "Paulo Freire critical pedagogy", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("sun_tzu", "孫子兵法 戰略", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    InterviewNewsFeed("leonardo_da_vinci", "Leonardo da Vinci documentary", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("abraham_lincoln", "Abraham Lincoln biography", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("albert_einstein", "Albert Einstein interview documentary", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("zhuge_liang", "諸葛亮 歷史", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    InterviewNewsFeed("napoleon_bonaparte", "Napoleon biography", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("marie_curie", "Marie Curie biography", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("winston_churchill", "Winston Churchill speech documentary", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("nikola_tesla", "Nikola Tesla documentary", "en", "en-US", "US", "US:en"),
    InterviewNewsFeed("aristotle", "Aristotle philosophy lecture", "en", "en-US", "US", "US:en"),
]

# --- YouTube 長訪談（有字幕）---
YOUTUBE_INTERVIEWS = [
    YouTubeSpeech("elon_musk", "rgwS24B_F90", "Joe Rogan Experience #1169 - Elon Musk", "en"),
    YouTubeSpeech("elon_musk", "SKSsnsAEcn8", "BBC News Interview - Elon Musk (2023)", "en"),
    YouTubeSpeech("elon_musk", "zxJMrb4Du04", "Elon Musk at TED2017", "en"),
    YouTubeSpeech("jensen_huang", "vif8NQcjVf0", "Lex Fridman Podcast #494 - Jensen Huang", "en"),
    YouTubeSpeech("steve_jobs", "ORpB8-NlWQ0", "Steve Jobs Interview - 1995 (Lost Interview excerpt)", "en"),
    YouTubeSpeech("steve_jobs", "ftf4riVJHhw", "Steve Jobs at D8 Conference 2010", "en"),
    YouTubeSpeech("bill_gates", "nLcNNDCW0VM", "Bill Gates on AI and the future (2024)", "en"),
    YouTubeSpeech("bill_gates", "6Af6b_wyiwI", "Bill Gates and Warren Buffett at Columbia (2017)", "en"),
    YouTubeSpeech("andrew_ng", "0jspaMLxBig", "Lex Fridman #73 - Andrew Ng", "en"),
    YouTubeSpeech("jeff_bezos", "MzCH9K4eInE", "Jeff Bezos interview", "en"),
    YouTubeSpeech("peter_thiel", "Ro7enGnDOeE", "Peter Thiel Lex Fridman", "en"),
]

# --- 網頁訪談稿（含公開逐字稿）---
WEB_INTERVIEWS = [
    WebSpeech(
        "elon_musk",
        "https://www.bbc.com/news/world-us-canada-65249139",
        "BBC Full Interview - Elon Musk (2023)",
        "en",
    ),
    WebSpeech(
        "jensen_huang",
        "https://lexfridman.com/jensen-huang-transcript/",
        "Lex Fridman Transcript - Jensen Huang (#494)",
        "en",
    ),
]


def google_news_rss_url(query: str, hl: str, gl: str, ceid: str) -> str:
    q = quote_plus(query)
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"


def strip_html(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_feed(url: str) -> feedparser.FeedParserDict:
    with requests.Session() as session:
        session.trust_env = False
        resp = session.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return feedparser.parse(resp.content)


def build_interview_content(
    title: str, summary: str, published: str, source_name: str, query: str
) -> str:
    parts = [
        f"[訪談報導] 標題：{title}",
        f"搜尋關鍵字：{query}",
    ]
    if published:
        parts.append(f"時間：{published}")
    if source_name:
        parts.append(f"媒體：{source_name}")
    if summary:
        parts.append(f"內容摘要：{summary}")
    return "\n".join(parts)


def crawl_interview_news(conn, person_slug: str | None = None) -> tuple[int, int, int]:
    ok, skip, fail = 0, 0, 0
    feeds = INTERVIEW_NEWS_FEEDS
    if person_slug:
        feeds = [f for f in INTERVIEW_NEWS_FEEDS if f.person_slug == person_slug]
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        print("【Google News 訪談報導】")
        for feed_cfg in feeds:
            url = google_news_rss_url(
                feed_cfg.query, feed_cfg.hl, feed_cfg.gl, feed_cfg.ceid
            )
            print(f"  {feed_cfg.person_slug}: {feed_cfg.query}")
            try:
                feed = fetch_feed(url)
                time.sleep(REQUEST_DELAY_SEC)
            except Exception as e:
                print(f"    ✗ RSS 失敗：{e}\n")
                fail += 1
                continue

            entries = feed.entries[:MAX_PER_FEED]
            person_id = get_person_id(cur, feed_cfg.person_slug)

            for entry in entries:
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

                raw = build_interview_content(
                    title, summary, published, source_name, feed_cfg.query
                )
                if len(raw) < MIN_INTERVIEW_CHARS:
                    skip += 1
                    continue

                try:
                    doc_id, n_chunks = save_document_and_chunks(
                        cur,
                        person_id=person_id,
                        source_url=link,
                        title=title,
                        raw_content=raw,
                        language=feed_cfg.language,
                        source_type="interview",
                        metadata={
                            "source": "google_news_rss_interview",
                            "query": feed_cfg.query,
                        },
                    )
                    conn.commit()
                    ok += 1
                except Exception as e:
                    conn.rollback()
                    fail += 1
                    print(f"    ✗ 寫入失敗：{e}")

            print(f"    本關鍵字處理 {len(entries)} 則\n")
    return ok, skip, fail


def crawl_youtube_interviews(conn, person_slug: str | None = None) -> tuple[int, int, int]:
    ok, skip, fail = 0, 0, 0
    items = YOUTUBE_INTERVIEWS
    if person_slug:
        items = [i for i in YOUTUBE_INTERVIEWS if i.person_slug == person_slug]
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        print("【YouTube 訪談字幕】")
        for item in items:
            source_url = f"https://www.youtube.com/watch?v={item.video_id}"
            print(f"  {item.person_slug}: {item.title}")
            text, method = fetch_youtube_transcript(item)
            time.sleep(REQUEST_DELAY_SEC)

            if not text:
                print("    → 跳過\n")
                skip += 1
                continue

            person_id = get_person_id(cur, item.person_slug)
            doc_id, n_chunks = save_document_and_chunks(
                cur,
                person_id=person_id,
                source_url=source_url,
                title=item.title,
                raw_content=text,
                language=item.language,
                source_type="interview",
                metadata={
                    "source": method,
                    "video_id": item.video_id,
                    "chars": len(text),
                },
            )
            conn.commit()
            ok += 1
            print(f"    → ✓ [{method}] {len(text)} 字, {n_chunks} chunks\n")
    return ok, skip, fail


def crawl_web_interviews(conn, person_slug: str | None = None) -> tuple[int, int, int]:
    ok, skip, fail = 0, 0, 0
    pages = WEB_INTERVIEWS
    if person_slug:
        pages = [p for p in WEB_INTERVIEWS if p.person_slug == person_slug]
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        print("【網頁訪談全文】")
        for page in pages:
            print(f"  {page.person_slug}: {page.title}")
            try:
                text = fetch_web_article(page)
                time.sleep(REQUEST_DELAY_SEC)
            except requests.RequestException as e:
                print(f"    → ✗ {e}\n")
                fail += 1
                continue

            if not text or len(text) < MIN_SPEECH_CHARS:
                print("    → 跳過（太短）\n")
                skip += 1
                continue

            person_id = get_person_id(cur, page.person_slug)
            doc_id, n_chunks = save_document_and_chunks(
                cur,
                person_id=person_id,
                source_url=page.url,
                title=page.title,
                raw_content=text,
                language=page.language,
                source_type="interview",
                metadata={"source": "trafilatura_web", "chars": len(text)},
            )
            conn.commit()
            ok += 1
            print(f"    → ✓ {len(text)} 字, {n_chunks} chunks\n")
    return ok, skip, fail


def main(person_slug: str | None = None) -> None:
    print("=== 訪談爬蟲 ===\n")
    conn = psycopg2.connect(**DB_CONFIG)
    total_ok = total_skip = total_fail = 0

    try:
        for func in (crawl_interview_news, crawl_youtube_interviews, crawl_web_interviews):
            o, s, f = func(conn, person_slug=person_slug)
            total_ok += o
            total_skip += s
            total_fail += f

        print(f"總計：成功 {total_ok}，跳過 {total_skip}，失敗 {total_fail}\n")
        print_stats(conn)
        print()
        print_stats_by_type(conn)
    finally:
        conn.close()

    print("\n完成。pgAdmin：SELECT * FROM documents WHERE source_type='interview';")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--person", help="只抓此人，例如 steve_jobs")
    args = p.parse_args()
    main(person_slug=args.person)
