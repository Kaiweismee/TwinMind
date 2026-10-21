"""
新聞爬蟲（第一步）：Google News RSS → documents + chunks

為什麼先用 RSS：
- 不需 API key，適合畢專起步
- 有標題、連結、摘要（來源可追溯）
- 比硬爬各家新聞網站穩定

之後第二步可再做：進入原文網址抓全文（news_article.py）

執行：
  cd ~/Desktop/digital_twin_project
  ./venv/bin/pip install -r requirements.txt
  ./venv/bin/python crawl/news_rss.py
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

HEADERS = {
    "User-Agent": "digital-twin-thesis-poc/1.0 (education; contact: local-dev)",
}

# 畢專建議：每關鍵字 25 則 × 約 12 組搜尋 ≈ 每人 100+ 則新聞（去重後實際會少一些）
MAX_PER_FEED = 25
REQUEST_DELAY_SEC = 1.2


@dataclass
class NewsFeed:
    person_slug: str
    query: str
    language: str  # 寫入 documents.language
    hl: str
    gl: str
    ceid: str


# 每個搜尋關鍵字對應一條 Google News RSS
# 涵蓋：公司、AI、訪談/發言、產品事件 — 適合數位分身 RAG 語料
NEWS_FEEDS = [
    # --- 馬斯克（中文）---
    NewsFeed("elon_musk", "埃隆·馬斯克 特斯拉", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("elon_musk", "馬斯克 SpaceX 星艦", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("elon_musk", "馬斯克 人工智慧 AI", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("elon_musk", "馬斯克 訪談", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("elon_musk", "馬斯克 xAI", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    # --- 馬斯克（英文）---
    NewsFeed("elon_musk", "Elon Musk Tesla", "en", "en-US", "US", "US:en"),
    NewsFeed("elon_musk", "Elon Musk SpaceX Starship", "en", "en-US", "US", "US:en"),
    NewsFeed("elon_musk", "Elon Musk interview AI", "en", "en-US", "US", "US:en"),
    NewsFeed("elon_musk", "Elon Musk xAI Grok", "en", "en-US", "US", "US:en"),
    # --- 黃仁勳（中文）---
    NewsFeed("jensen_huang", "黃仁勳 NVIDIA", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("jensen_huang", "黃仁勳 輝達 AI", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("jensen_huang", "黃仁勳 演講 GTC", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("jensen_huang", "黃仁勳 訪談", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("jensen_huang", "輝達 財報 黃仁勳", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    # --- 黃仁勳（英文）---
    NewsFeed("jensen_huang", "Jensen Huang NVIDIA", "en", "en-US", "US", "US:en"),
    NewsFeed("jensen_huang", "Jensen Huang AI keynote", "en", "en-US", "US", "US:en"),
    NewsFeed("jensen_huang", "Jensen Huang interview", "en", "en-US", "US", "US:en"),
    NewsFeed("jensen_huang", "NVIDIA GTC Jensen Huang", "en", "en-US", "US", "US:en"),
    # --- 賈伯斯（中文）---
    NewsFeed("steve_jobs", "史蒂夫·賈伯斯 蘋果", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("steve_jobs", "賈伯斯 演講", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("steve_jobs", "賈伯斯 iPhone", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("steve_jobs", "乔布斯 苹果", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    # --- 賈伯斯（英文）---
    NewsFeed("steve_jobs", "Steve Jobs Apple", "en", "en-US", "US", "US:en"),
    NewsFeed("steve_jobs", "Steve Jobs interview", "en", "en-US", "US", "US:en"),
    NewsFeed("steve_jobs", "Steve Jobs iPhone keynote", "en", "en-US", "US", "US:en"),
    # --- 蓋茲（中文）---
    NewsFeed("bill_gates", "比爾·蓋茲 微軟", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("bill_gates", "蓋茲 慈善 基金會", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("bill_gates", "蓋茲 人工智慧 AI", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("bill_gates", "蓋茲 氣候變遷", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("bill_gates", "比尔盖茨 微软", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    # --- 蓋茲（英文）---
    NewsFeed("bill_gates", "Bill Gates Microsoft", "en", "en-US", "US", "US:en"),
    NewsFeed("bill_gates", "Bill Gates philanthropy", "en", "en-US", "US", "US:en"),
    NewsFeed("bill_gates", "Bill Gates climate energy", "en", "en-US", "US", "US:en"),
    NewsFeed("bill_gates", "Bill Gates interview AI", "en", "en-US", "US", "US:en"),
    # --- 吳恩達（中文）---
    NewsFeed("andrew_ng", "吳恩達 機器學習", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("andrew_ng", "吳恩達 深度學習 AI", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("andrew_ng", "吳恩達 Coursera", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("andrew_ng", "吴恩达 人工智能", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    # --- 吳恩達（英文）---
    NewsFeed("andrew_ng", "Andrew Ng machine learning", "en", "en-US", "US", "US:en"),
    NewsFeed("andrew_ng", "Andrew Ng DeepLearning.AI", "en", "en-US", "US", "US:en"),
    NewsFeed("andrew_ng", "Andrew Ng interview AI", "en", "en-US", "US", "US:en"),
    NewsFeed("andrew_ng", "Andrew Ng Stanford", "en", "en-US", "US", "US:en"),
    # --- 批次名人（中文）---
    NewsFeed("jeff_bezos", "貝佐斯 亞馬遜", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("jeff_bezos", "Jeff Bezos Amazon", "en", "en-US", "US", "US:en"),
    NewsFeed("ray_dalio", "達利歐 橋水", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("ray_dalio", "Ray Dalio Bridgewater", "en", "en-US", "US", "US:en"),
    NewsFeed("morris_chang", "張忠謀 台積電", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("morris_chang", "Morris Chang TSMC", "en", "en-US", "US", "US:en"),
    NewsFeed("charlie_munger", "蒙格 波克夏", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("charlie_munger", "Charlie Munger Berkshire", "en", "en-US", "US", "US:en"),
    NewsFeed("peter_thiel", "提爾 Palantir", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("peter_thiel", "Peter Thiel interview", "en", "en-US", "US", "US:en"),
    NewsFeed("indra_nooyi", "努伊 PepsiCo", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("indra_nooyi", "Indra Nooyi interview", "en", "en-US", "US", "US:en"),
    NewsFeed("michael_porter", "麥可波特 策略", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("michael_porter", "Michael Porter strategy", "en", "en-US", "US", "US:en"),
    NewsFeed("sheryl_sandberg", "桑德伯格 Meta", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("sheryl_sandberg", "Sheryl Sandberg interview", "en", "en-US", "US", "US:en"),
    NewsFeed("terry_gou", "郭台銘 鴻海", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("terry_gou", "Terry Gou Foxconn", "en", "en-US", "US", "US:en"),
    # --- 教育家／思想家 ---
    NewsFeed("confucius", "孔子 儒家", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("confucius", "論語 教育", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("confucius", "Confucius philosophy", "en", "en-US", "US", "US:en"),
    NewsFeed("peter_drucker", "彼得杜拉克 管理", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("peter_drucker", "Peter Drucker management", "en", "en-US", "US", "US:en"),
    NewsFeed("ken_robinson", "肯羅賓森 創意 教育", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("ken_robinson", "Ken Robinson education creativity", "en", "en-US", "US", "US:en"),
    NewsFeed("sal_khan", "可汗學院 Khan Academy", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("sal_khan", "Sal Khan interview education", "en", "en-US", "US", "US:en"),
    NewsFeed("john_dewey", "杜威 教育 哲學", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("john_dewey", "John Dewey education pragmatism", "en", "en-US", "US", "US:en"),
    NewsFeed("maria_montessori", "蒙特梭利 教育", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("maria_montessori", "Maria Montessori method", "en", "en-US", "US", "US:en"),
    NewsFeed("sugata_mitra", "蘇伽特米特拉 教育", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("sugata_mitra", "Sugata Mitra SOLE education", "en", "en-US", "US", "US:en"),
    NewsFeed("carol_dweck", "卡羅杜維克 成長心態", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("carol_dweck", "Carol Dweck growth mindset", "en", "en-US", "US", "US:en"),
    NewsFeed("howard_gardner", "迦納 多元智能", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("howard_gardner", "Howard Gardner multiple intelligences", "en", "en-US", "US", "US:en"),
    NewsFeed("paulo_freire", "弗雷勒 教育 解放", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("paulo_freire", "Paulo Freire pedagogy oppressed", "en", "en-US", "US", "US:en"),
    # --- 歷史人物 ---
    NewsFeed("sun_tzu", "孫子 兵法", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("sun_tzu", "Sun Tzu Art of War", "en", "en-US", "US", "US:en"),
    NewsFeed("leonardo_da_vinci", "達文西 藝術 科學", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("leonardo_da_vinci", "Leonardo da Vinci biography", "en", "en-US", "US", "US:en"),
    NewsFeed("abraham_lincoln", "林肯 美國總統", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("abraham_lincoln", "Abraham Lincoln Civil War", "en", "en-US", "US", "US:en"),
    NewsFeed("albert_einstein", "愛因斯坦 相對論", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("albert_einstein", "Albert Einstein physics", "en", "en-US", "US", "US:en"),
    NewsFeed("zhuge_liang", "諸葛亮 三國", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("zhuge_liang", "Zhuge Liang Three Kingdoms", "en", "en-US", "US", "US:en"),
    NewsFeed("napoleon_bonaparte", "拿破崙 歐洲", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("napoleon_bonaparte", "Napoleon Bonaparte history", "en", "en-US", "US", "US:en"),
    NewsFeed("marie_curie", "居禮夫人 諾貝爾", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("marie_curie", "Marie Curie radioactivity", "en", "en-US", "US", "US:en"),
    NewsFeed("winston_churchill", "邱吉爾 二戰", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("winston_churchill", "Winston Churchill World War II", "en", "en-US", "US", "US:en"),
    NewsFeed("nikola_tesla", "特斯拉 發明", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("nikola_tesla", "Nikola Tesla electricity", "en", "en-US", "US", "US:en"),
    NewsFeed("aristotle", "亞里斯多德 哲學", "zh", "zh-TW", "TW", "TW:zh-Hant"),
    NewsFeed("aristotle", "Aristotle philosophy ethics", "en", "en-US", "US", "US:en"),
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


def build_raw_content(title: str, summary: str, published: str, source_name: str) -> str:
    parts = [f"標題：{title}"]
    if published:
        parts.append(f"時間：{published}")
    if source_name:
        parts.append(f"來源：{source_name}")
    if summary:
        parts.append(f"摘要：{summary}")
    return "\n".join(parts)


def print_stats_by_type(conn) -> None:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT p.name_zh, d.source_type, COUNT(*) AS n
            FROM documents d
            JOIN persons p ON p.id = d.person_id
            GROUP BY p.name_zh, d.source_type
            ORDER BY p.name_zh, d.source_type;
            """
        )
        print("--- 依類型統計 ---")
        for row in cur.fetchall():
            print(f"  {row['name_zh']} / {row['source_type']}: {row['n']} 篇")


def main(person_slug: str | None = None) -> None:
    print("=== 新聞 RSS 爬蟲（第一步）===\n")
    feeds = NEWS_FEEDS
    if person_slug:
        feeds = [f for f in NEWS_FEEDS if f.person_slug == person_slug]

    conn = psycopg2.connect(**DB_CONFIG)
    ok, skip, fail = 0, 0, 0

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for feed_cfg in feeds:
                url = google_news_rss_url(
                    feed_cfg.query, feed_cfg.hl, feed_cfg.gl, feed_cfg.ceid
                )
                print(f"【{feed_cfg.person_slug}】搜尋：{feed_cfg.query}")
                print(f"  RSS: {url}")

                try:
                    feed = fetch_feed(url)
                    time.sleep(REQUEST_DELAY_SEC)
                except Exception as e:
                    print(f"  ✗ 讀取 RSS 失敗：{e}\n")
                    fail += 1
                    continue

                entries = feed.entries[:MAX_PER_FEED]
                print(f"  取得 {len(entries)} 則（上限 {MAX_PER_FEED}）\n")
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

                    raw_content = build_raw_content(
                        title, summary, published, source_name
                    )
                    if len(raw_content) < 30:
                        skip += 1
                        continue

                    try:
                        doc_id, n_chunks = save_document_and_chunks(
                            cur,
                            person_id=person_id,
                            source_url=link,
                            title=title,
                            raw_content=raw_content,
                            language=feed_cfg.language,
                            source_type="news",
                            metadata={
                                "source": "google_news_rss",
                                "query": feed_cfg.query,
                                "published": published,
                                "publisher": source_name,
                            },
                        )
                        conn.commit()
                        ok += 1
                        preview = title[:50] + ("…" if len(title) > 50 else "")
                        print(f"  ✓ [{doc_id}] {preview} ({n_chunks} chunks)")
                    except Exception as e:
                        conn.rollback()
                        fail += 1
                        print(f"  ✗ 寫入失敗：{title[:40]}… → {e}")

                print()

        print(f"本輪：成功 {ok} 則，跳過 {skip} 則，失敗 {fail} 則\n")
        print_stats(conn)
        print()
        print_stats_by_type(conn)
    finally:
        conn.close()

    print("\n完成。pgAdmin 執行：SELECT * FROM documents WHERE source_type='news';")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--person", help="只抓此人，例如 steve_jobs")
    args = p.parse_args()
    main(person_slug=args.person)
