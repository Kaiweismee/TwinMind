"""
擴充爬蟲：每位名人抓多篇維基（較長內文，不只第一行摘要）

執行：
  cd ~/Desktop/digital_twin_project
  ./venv/bin/python crawl/wikipedia_more.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from urllib.parse import quote

import psycopg2
import requests
from psycopg2.extras import RealDictCursor

sys.path.insert(0, str(Path(__file__).parent))
from db_utils import (
    DB_CONFIG,
    get_person_id,
    print_stats,
    save_document_and_chunks,
)

HEADERS = {
    "User-Agent": "digital-twin-thesis-poc/1.0 (education; contact: local-dev)",
}

# 每位名人要抓的維基頁面（lang, 頁面標題）
# 中文抓不完可保留英文頁；已存在的 URL 會更新內容，不會重複兩筆
PAGES_BY_PERSON: dict[str, list[tuple[str, str]]] = {
    "elon_musk": [
        ("zh", "埃隆·马斯克"),
        ("zh", "特斯拉 (公司)"),
        ("zh", "SpaceX"),
        ("zh", "星艦"),
        ("en", "Elon_Musk"),
        ("en", "Tesla, Inc."),
        ("en", "SpaceX"),
    ],
    "jensen_huang": [
        ("zh", "黃仁勳"),
        ("zh", "英伟达"),
        ("zh", "人工智能"),
        ("zh", "深度学习"),
        ("en", "Jensen_Huang"),
        ("en", "Nvidia"),
        ("en", "Deep_learning"),
    ],
    "steve_jobs": [
        ("zh", "史蒂夫·乔布斯"),
        ("zh", "苹果公司"),
        ("zh", "iPhone"),
        ("zh", "Macintosh"),
        ("en", "Steve_Jobs"),
        ("en", "Apple_Inc."),
        ("en", "IPhone"),
    ],
    "bill_gates": [
        ("zh", "比尔·盖茨"),
        ("zh", "微软"),
        ("zh", "盖茨基金会"),
        ("zh", "人工智能"),
        ("en", "Bill_Gates"),
        ("en", "Microsoft"),
        ("en", "Bill_%26_Melinda_Gates_Foundation"),
    ],
    "andrew_ng": [
        ("zh", "吴恩达"),
        ("zh", "机器学习"),
        ("zh", "深度学习"),
        ("zh", "Coursera"),
        ("en", "Andrew_Ng"),
        ("en", "Machine_learning"),
        ("en", "Coursera"),
        ("en", "Deep_learning"),
    ],
    "jeff_bezos": [("zh", "杰夫·贝佐斯"), ("en", "Jeff_Bezos"), ("en", "Amazon")],
    "ray_dalio": [("zh", "瑞·达利欧"), ("en", "Ray_Dalio"), ("en", "Bridgewater_Associates")],
    "morris_chang": [("zh", "张忠谋"), ("zh", "台积电"), ("en", "Morris_Chang"), ("en", "TSMC")],
    "charlie_munger": [("zh", "查理·芒格"), ("en", "Charlie_Munger"), ("en", "Berkshire_Hathaway")],
    "peter_thiel": [("en", "Peter_Thiel"), ("en", "Palantir"), ("en", "PayPal")],
    "indra_nooyi": [("en", "Indra_Nooyi"), ("en", "PepsiCo")],
    "michael_porter": [("en", "Michael_Porter"), ("en", "Competitive_advantage")],
    "sheryl_sandberg": [("en", "Sheryl_Sandberg"), ("en", "Meta_Platforms")],
    "terry_gou": [("zh", "郭台铭"), ("zh", "鸿海精密"), ("en", "Terry_Gou"), ("en", "Foxconn")],
    "confucius": [
        ("zh", "孔子"),
        ("zh", "儒家"),
        ("zh", "论语"),
        ("en", "Confucius"),
        ("en", "Confucianism"),
    ],
    "peter_drucker": [("zh", "彼得·德鲁克"), ("en", "Peter_Drucker"), ("en", "Management")],
    "ken_robinson": [("en", "Ken_Robinson_(educationalist)"), ("en", "Creativity")],
    "sal_khan": [("en", "Sal_Khan"), ("en", "Khan_Academy"), ("zh", "可汗学院")],
    "john_dewey": [("zh", "约翰·杜威"), ("en", "John_Dewey"), ("en", "Pragmatism")],
    "maria_montessori": [("en", "Maria_Montessori"), ("en", "Montessori_education")],
    "sugata_mitra": [("en", "Sugata_Mitra"), ("en", "Minimally_invasive_education")],
    "carol_dweck": [("en", "Carol_Dweck"), ("en", "Growth_mindset")],
    "howard_gardner": [("en", "Howard_Gardner"), ("en", "Theory_of_multiple_intelligences")],
    "paulo_freire": [("en", "Paulo_Freire"), ("en", "Pedagogy_of_the_Oppressed")],
    "sun_tzu": [
        ("zh", "孙子"),
        ("zh", "孙子兵法"),
        ("zh", "兵法"),
        ("en", "Sun_Tzu"),
        ("en", "The_Art_of_War"),
    ],
    "leonardo_da_vinci": [
        ("zh", "列奥纳多·达·芬奇"),
        ("zh", "文艺复兴"),
        ("en", "Leonardo_da_Vinci"),
        ("en", "Renaissance"),
    ],
    "abraham_lincoln": [
        ("zh", "亚伯拉罕·林肯"),
        ("zh", "美国内战"),
        ("en", "Abraham_Lincoln"),
        ("en", "American_Civil_War"),
    ],
    "albert_einstein": [
        ("zh", "阿尔伯特·爱因斯坦"),
        ("zh", "相对论"),
        ("en", "Albert_Einstein"),
        ("en", "Theory_of_relativity"),
        ("en", "General_relativity"),
    ],
    "zhuge_liang": [
        ("zh", "诸葛亮"),
        ("zh", "三国"),
        ("zh", "蜀汉"),
        ("en", "Zhuge_Liang"),
        ("en", "Three_Kingdoms"),
    ],
    "napoleon_bonaparte": [
        ("zh", "拿破仑"),
        ("zh", "法兰西第一帝国"),
        ("en", "Napoleon"),
        ("en", "Napoleonic_Wars"),
    ],
    "marie_curie": [
        ("zh", "玛丽·居里"),
        ("zh", "放射性"),
        ("en", "Marie_Curie"),
        ("en", "Radioactive"),
    ],
    "winston_churchill": [
        ("zh", "温斯顿·丘吉尔"),
        ("zh", "第二次世界大战"),
        ("en", "Winston_Churchill"),
        ("en", "World_War_II"),
    ],
    "nikola_tesla": [
        ("zh", "尼古拉·特斯拉"),
        ("zh", "交流电"),
        ("en", "Nikola_Tesla"),
        ("en", "Alternating_current"),
    ],
    "aristotle": [
        ("zh", "亚里士多德"),
        ("zh", "古希腊哲学"),
        ("en", "Aristotle"),
        ("en", "Ancient_Greek_philosophy"),
        ("en", "Ethics"),
    ],
}

EXTRACT_MAX_CHARS = 12000
REQUEST_DELAY_SEC = 1.0


def fetch_wiki_full_text(lang: str, title: str) -> tuple[str, str, str] | None:
    """
    用 MediaWiki API 抓較長純文字。
    回傳 (內文, 頁面網址, 解析後標題)；失敗回傳 None。
    """
    api = f"https://{lang}.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts",
        "explaintext": True,
        "exsectionformat": "plain",
        "exchars": EXTRACT_MAX_CHARS,
        "titles": title,
        "redirects": 1,
    }

    with requests.Session() as session:
        session.trust_env = False
        resp = session.get(api, params=params, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    pages = data.get("query", {}).get("pages", {})
    if not pages:
        return None

    page = next(iter(pages.values()))
    if page.get("missing") or page.get("invalid"):
        return None

    extract = (page.get("extract") or "").strip()
    if len(extract) < 80:
        return None

    resolved = page.get("title") or title
    page_url = f"https://{lang}.wikipedia.org/wiki/{quote(resolved.replace(' ', '_'))}"
    return extract, page_url, resolved


def main(person_slug: str | None = None) -> None:
    print("=== 維基百科擴充爬蟲（多篇 / 較長內文）===\n")
    pages_map = PAGES_BY_PERSON
    if person_slug:
        pages_map = {person_slug: PAGES_BY_PERSON[person_slug]}

    conn = psycopg2.connect(**DB_CONFIG)
    ok, skip, fail = 0, 0, 0

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            for slug, pages in pages_map.items():
                person_slug = slug
                person_id = get_person_id(cur, person_slug)
                print(f"【{person_slug}】")

                for lang, title in pages:
                    label = f"  ({lang}) {title}"
                    try:
                        result = fetch_wiki_full_text(lang, title)
                        time.sleep(REQUEST_DELAY_SEC)

                        if not result:
                            print(f"{label} → 跳過（無內容或頁面不存在）")
                            skip += 1
                            continue

                        extract, source_url, resolved_title = result
                        doc_id, n_chunks = save_document_and_chunks(
                            cur,
                            person_id=person_id,
                            source_url=source_url,
                            title=resolved_title,
                            raw_content=extract,
                            language=lang,
                            metadata={
                                "source": "wikipedia_mediawiki_extract",
                                "wiki_title": title,
                                "chars": len(extract),
                            },
                        )
                        conn.commit()
                        ok += 1
                        print(
                            f"{label} → ✓ doc_id={doc_id}, "
                            f"{len(extract)} 字, {n_chunks} chunks"
                        )
                    except requests.RequestException as e:
                        fail += 1
                        print(f"{label} → ✗ 連線失敗：{e}")
                    except Exception as e:
                        fail += 1
                        print(f"{label} → ✗ 錯誤：{e}")

                print()

        print(f"完成：成功 {ok} 篇，跳過 {skip} 篇，失敗 {fail} 篇\n")
        print_stats(conn)
    finally:
        conn.close()

    print("\n請到 pgAdmin 重新整理 documents / chunks 查看。")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--person", help="只抓此人，例如 steve_jobs")
    args = p.parse_args()
    main(person_slug=args.person)
