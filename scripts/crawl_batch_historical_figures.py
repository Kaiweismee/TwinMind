#!/usr/bin/env python3
"""
批次爬取 10 位歷史人物：person_auto → 補強維基／演講／訪談／新聞 → 向量化

用法：
  cd ~/Desktop/digital_twin_project
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
  ./venv/bin/python scripts/crawl_batch_historical_figures.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / "venv" / "bin" / "python"

# slug, 中文名, 英文名, 關鍵字, 手動 YouTube, 額外維基
FIGURES: list[tuple[str, str, str, str, str, str]] = [
    (
        "sun_tzu",
        "孫子",
        "Sun Tzu",
        "兵法 孫子兵法",
        "",
        "zh:孙子,zh:孙子兵法,en:Sun_Tzu,en:The_Art_of_War",
    ),
    (
        "leonardo_da_vinci",
        "李奧納多·達文西",
        "Leonardo da Vinci",
        "Renaissance art invention",
        "",
        "zh:列奥纳多·达·芬奇,en:Leonardo_da_Vinci",
    ),
    (
        "abraham_lincoln",
        "亞伯拉罕·林肯",
        "Abraham Lincoln",
        "Civil War Emancipation",
        "aAgX5wWM5X4:Gettysburg Address",
        "en:Abraham_Lincoln,zh:亚伯拉罕·林肯",
    ),
    (
        "albert_einstein",
        "阿爾伯特·愛因斯坦",
        "Albert Einstein",
        "Relativity physics Nobel",
        "mg8mqvOfXDI:Interview 1955",
        "en:Albert_Einstein,zh:阿尔伯特·爱因斯坦",
    ),
    (
        "zhuge_liang",
        "諸葛亮",
        "Zhuge Liang",
        "三國 蜀漢",
        "",
        "zh:诸葛亮,zh:三国,en:Zhuge_Liang",
    ),
    (
        "napoleon_bonaparte",
        "拿破崙",
        "Napoleon Bonaparte",
        "Napoleonic Wars France",
        "",
        "zh:拿破仑,en:Napoleon,en:Napoleonic_Wars",
    ),
    (
        "marie_curie",
        "瑪麗·居禮",
        "Marie Curie",
        "Radioactivity Nobel physics chemistry",
        "GGyLOi0EA0w:Biography documentary",
        "en:Marie_Curie,zh:玛丽·居里",
    ),
    (
        "winston_churchill",
        "溫斯頓·邱吉爾",
        "Winston Churchill",
        "World War II Britain",
        "jM3z14c3OSU:Blood Toil Tears and Sweat",
        "en:Winston_Churchill,zh:温斯顿·丘吉尔",
    ),
    (
        "nikola_tesla",
        "尼古拉·特斯拉",
        "Nikola Tesla",
        "AC electricity invention",
        "3J7bAZNGht8:Documentary",
        "en:Nikola_Tesla,zh:尼古拉·特斯拉",
    ),
    (
        "aristotle",
        "亞里斯多德",
        "Aristotle",
        "Philosophy ethics logic",
        "PrvtOWEXDIQ:Crash Course Aristotle",
        "en:Aristotle,zh:亚里士多德",
    ),
]

SLUGS = [t[0] for t in FIGURES]


def run_person(
    slug: str,
    name_zh: str,
    name_en: str,
    company: str,
    youtube: str,
    wiki_pages: str,
) -> int:
    cmd = [
        str(PY),
        str(ROOT / "crawl" / "person_auto.py"),
        "--name-zh",
        name_zh,
        "--name-en",
        name_en,
        "--company",
        company,
        "--slug",
        slug,
        "--youtube-max",
        "8",
        "--skip-embed-hint",
    ]
    if youtube:
        cmd.extend(["--youtube", youtube])
    if wiki_pages:
        cmd.extend(["--wiki-pages", wiki_pages])
    print("\n" + "=" * 60)
    print(f">>> {name_zh} / {name_en} ({slug})")
    print("=" * 60)
    return subprocess.call(cmd, cwd=ROOT)


def run_supplementary() -> None:
    print("\n" + "=" * 60)
    print(">>> 補強：多篇維基 + 清單內 YouTube + 訪談 RSS + 新聞 RSS")
    print("=" * 60)
    scripts = [
        "crawl/wikipedia_more.py",
        "crawl/speech_fetch.py",
        "crawl/interview_fetch.py",
        "crawl/news_rss.py",
    ]
    for slug in SLUGS:
        for script in scripts:
            print(f"\n--- {script} --person {slug} ---")
            subprocess.run(
                [str(PY), str(ROOT / script), "--person", slug],
                cwd=ROOT,
                check=False,
            )


def main() -> None:
    if not PY.exists():
        print(f"找不到 {PY}，請先建立 venv")
        sys.exit(1)

    failed: list[str] = []
    for slug, zh, en, co, yt, wiki in FIGURES:
        code = run_person(slug, zh, en, co, yt, wiki)
        if code != 0:
            failed.append(slug)
            print(f"⚠ {slug} 結束碼 {code}（可能部分失敗，繼續下一位）")

    run_supplementary()

    print("\n" + "=" * 60)
    print(">>> 向量化")
    print("=" * 60)
    subprocess.run(
        [str(PY), str(ROOT / "rag" / "embed_chunks.py"), "--no-index"],
        cwd=ROOT,
        check=False,
    )

    print("\n=== 批次完成 ===")
    if failed:
        print("person_auto 非零結束碼：", ", ".join(failed))
    print("檢查 SQL：")
    print(
        "  SELECT p.slug, d.source_type, COUNT(*) FROM documents d\n"
        "  JOIN persons p ON p.id=d.person_id\n"
        "  WHERE p.slug IN (" + ",".join(f"'{s}'" for s in SLUGS) + ")\n"
        "  GROUP BY p.slug, d.source_type ORDER BY p.slug;"
    )


if __name__ == "__main__":
    main()
