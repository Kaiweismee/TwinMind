"""
可行性測試：用維基百科 API 抓少量公開摘要 → 寫入 documents + chunks

為什麼用維基：
- 有官方 API，比硬爬網頁穩定
- 適合畢專 POC（之後可換成新聞、演講稿來源）

執行：
  cd ~/Desktop/digital_twin_project
  ./venv/bin/pip install -r requirements.txt
  ./venv/bin/python crawl/wikipedia_poc.py
"""

from __future__ import annotations

import hashlib
import json
import re
import textwrap
from dataclasses import dataclass
from typing import Any

import psycopg2
import requests
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "digital_twin",
    "user": "kaiwei",
}

WIKI_API = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
CHUNK_SIZE = 400  # 字元數，POC 用簡單切塊

HEADERS = {
    "User-Agent": "digital-twin-thesis-poc/1.0 (education; contact: local-dev)",
}


@dataclass
class WikiTarget:
    person_slug: str
    lang: str
    title: str  # 維基頁面標題，需與 URL 一致


TARGETS = [
    WikiTarget("elon_musk", "zh", "伊隆·马斯克"),
    WikiTarget("jensen_huang", "zh", "黃仁勳"),
    # 若中文標題失敗，可改用英文（把下面兩行取消註解，上面改註解）
    # WikiTarget("elon_musk", "en", "Elon_Musk"),
    # WikiTarget("jensen_huang", "en", "Jensen_Huang"),
]


def fetch_wiki_summary(lang: str, title: str) -> dict[str, Any]:
    url = WIKI_API.format(lang=lang, title=title)
    # 避免本機錯誤的 HTTP_PROXY 導致連線失敗
    with requests.Session() as session:
        session.trust_env = False
        resp = session.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def split_chunks(text: str, size: int = CHUNK_SIZE) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    return textwrap.wrap(text, width=size, break_long_words=False, break_on_hyphens=False)


def get_person_id(cur, slug: str) -> int:
    cur.execute("SELECT id FROM persons WHERE slug = %s;", (slug,))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"找不到名人 slug={slug}，請先執行 db/schema.sql")
    return row["id"]


def save_document_and_chunks(
    cur,
    person_id: int,
    source_url: str,
    title: str,
    raw_content: str,
    language: str,
    metadata: dict[str, Any],
) -> tuple[int, int]:
    h = content_hash(raw_content)

    cur.execute(
        """
        INSERT INTO documents (
            person_id, source_url, title, source_type, language,
            raw_content, content_hash
        ) VALUES (%s, %s, %s, 'wiki', %s, %s, %s)
        ON CONFLICT (person_id, source_url)
        DO UPDATE SET
            title = EXCLUDED.title,
            raw_content = EXCLUDED.raw_content,
            content_hash = EXCLUDED.content_hash,
            scraped_at = NOW(),
            updated_at = NOW()
        RETURNING id;
        """,
        (person_id, source_url, title, language, raw_content, h),
    )
    document_id = cur.fetchone()["id"]

    cur.execute("DELETE FROM chunks WHERE document_id = %s;", (document_id,))

    parts = split_chunks(raw_content)
    if not parts:
        parts = [raw_content]

    for idx, part in enumerate(parts):
        cur.execute(
            """
            INSERT INTO chunks (document_id, person_id, chunk_index, content, metadata)
            VALUES (%s, %s, %s, %s, %s);
            """,
            (
                document_id,
                person_id,
                idx,
                part,
                json.dumps({**metadata, "chunk_chars": len(part)}, ensure_ascii=False),
            ),
        )

    return document_id, len(parts)


def main() -> None:
    print("=== 維基百科 POC 爬蟲（可行性測試）===\n")

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for t in TARGETS:
                print(f"抓取：{t.person_slug} ({t.lang}) → {t.title}")
                try:
                    data = fetch_wiki_summary(t.lang, t.title)
                except requests.RequestException as e:
                    print(f"  ✗ 連線失敗：{e}")
                    print("  提示：檢查網路；或改 crawl/wikipedia_poc.py 用英文 Elon_Musk / Jensen_Huang\n")
                    continue

                extract = (data.get("extract") or "").strip()
                if not extract:
                    print("  ✗ 沒有摘要文字，跳過\n")
                    continue

                source_url = data.get("content_urls", {}).get("desktop", {}).get("page", "")
                if not source_url:
                    source_url = f"https://{t.lang}.wikipedia.org/wiki/{t.title}"

                title = data.get("title") or t.title
                person_id = get_person_id(cur, t.person_slug)
                doc_id, n_chunks = save_document_and_chunks(
                    cur,
                    person_id=person_id,
                    source_url=source_url,
                    title=title,
                    raw_content=extract,
                    language=t.lang,
                    metadata={
                        "source": "wikipedia_rest_summary",
                        "wiki_title": t.title,
                        "description": data.get("description"),
                    },
                )
                conn.commit()
                print(f"  ✓ document_id={doc_id}，chunks={n_chunks}")
                print(f"    預覽：{extract[:80]}...\n")

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT p.name_zh, COUNT(DISTINCT d.id) AS docs, COUNT(c.id) AS chunks
                FROM persons p
                LEFT JOIN documents d ON d.person_id = p.id
                LEFT JOIN chunks c ON c.person_id = p.id
                GROUP BY p.id, p.name_zh
                ORDER BY p.id;
                """
            )
            print("--- 資料庫統計 ---")
            for row in cur.fetchall():
                print(f"  {row['name_zh']}: {row['docs']} 篇文件, {row['chunks']} 個 chunks")
    finally:
        conn.close()

    print("\n完成。請到 pgAdmin 查看 documents / chunks 表。")


if __name__ == "__main__":
    main()
