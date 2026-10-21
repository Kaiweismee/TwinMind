#!/usr/bin/env python3
"""
批次爬取 10 位教育家／思想家：person_auto → 補強維基／演講／訪談／新聞 → 向量化

用法：
  cd ~/Desktop/digital_twin_project
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
  ./venv/bin/python scripts/crawl_batch_education_thinkers.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / "venv" / "bin" / "python"

# slug, 中文名, 英文名, 公司/關鍵字, 手動 YouTube, 額外維基
FIGURES: list[tuple[str, str, str, str, str, str]] = [
    (
        "confucius",
        "孔子",
        "Confucius",
        "儒家 論語",
        "",
        "zh:孔子,en:Confucius,zh:儒家",
    ),
    (
        "peter_drucker",
        "彼得·杜拉克",
        "Peter Drucker",
        "Management innovation",
        "HhE2eCqdovw:Legacy documentary",
        "en:Peter_Drucker,en:Management",
    ),
    (
        "ken_robinson",
        "肯·羅賓森",
        "Ken Robinson",
        "Education creativity TED",
        "iG9C55XpBU:Schools kill creativity,r9KhyYYyETo:Learning revolution",
        "en:Ken_Robinson_(educationalist),en:Creativity",
    ),
    (
        "sal_khan",
        "薩爾·可汗",
        "Sal Khan",
        "Khan Academy education",
        "gM95HHI4gLk:TED reinvent education",
        "en:Sal_Khan,en:Khan_Academy",
    ),
    (
        "john_dewey",
        "約翰·杜威",
        "John Dewey",
        "Pragmatism progressive education",
        "",
        "en:John_Dewey,en:Pragmatism",
    ),
    (
        "maria_montessori",
        "瑪利亞·蒙特梭利",
        "Maria Montessori",
        "Montessori method",
        "",
        "en:Maria_Montessori,en:Montessori_education",
    ),
    (
        "sugata_mitra",
        "蘇伽特·米特拉",
        "Sugata Mitra",
        "SOLE Hole in the Wall",
        "BECNs71GHsA:TED School in the Cloud",
        "en:Sugata_Mitra",
    ),
    (
        "carol_dweck",
        "卡羅·德韋克",
        "Carol Dweck",
        "Stanford growth mindset",
        "J-swZaKN2Ic:Power of yet TEDx",
        "en:Carol_Dweck,en:Mindset",
    ),
    (
        "howard_gardner",
        "霍華·嘉納",
        "Howard Gardner",
        "Harvard multiple intelligences",
        "8N2pnYne0ZA:MI lecture,IfzrN2yMBaQ:TEDx Beacon",
        "en:Howard_Gardner,en:Theory_of_multiple_intelligences",
    ),
    (
        "paulo_freire",
        "保羅·弗雷勒",
        "Paulo Freire",
        "Critical pedagogy liberating education",
        "",
        "en:Paulo_Freire,en:Pedagogy_of_the_Oppressed",
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
    """使用 news_rss / wikipedia_more / speech / interview 中已擴充的名人清單"""
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
    print("檢查（僅此 10 人）：")
    print(
        "  SELECT p.slug, d.source_type, COUNT(*) FROM documents d\n"
        "  JOIN persons p ON p.id=d.person_id\n"
        "  WHERE p.slug IN (" + ",".join(f"'{s}'" for s in SLUGS) + ")\n"
        "  GROUP BY p.slug, d.source_type ORDER BY p.slug;"
    )


if __name__ == "__main__":
    main()
