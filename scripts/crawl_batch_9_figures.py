#!/usr/bin/env python3
"""
批次爬取 9 位名人（person_auto 全流程），最後統一向量化。

用法：
  cd ~/Desktop/digital_twin_project
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
  ./venv/bin/python scripts/crawl_batch_9_figures.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = ROOT / "venv" / "bin" / "python"

# slug, 中文名, 英文名, 公司/關鍵字, 手動 YouTube（可空）, 額外維基
FIGURES: list[tuple[str, str, str, str, str, str]] = [
    (
        "jeff_bezos",
        "傑夫·貝佐斯",
        "Jeff Bezos",
        "Amazon Blue Origin",
        "vKJr8kqRkaU:Princeton 2010,MzCH9K4eInE:Interview",
        "zh:杰夫·贝佐斯,en:Jeff_Bezos,en:Amazon",
    ),
    (
        "ray_dalio",
        "瑞·達利歐",
        "Ray Dalio",
        "Bridgewater",
        "U4s4RWmv8WI:How to build a company",
        "en:Ray_Dalio,en:Bridgewater_Associates",
    ),
    (
        "morris_chang",
        "張忠謀",
        "Morris Chang",
        "TSMC 台積電",
        "",
        "zh:张忠谋,zh:台积电,en:Morris_Chang,en:TSMC",
    ),
    (
        "charlie_munger",
        "查理·蒙格",
        "Charlie Munger",
        "Berkshire Hathaway",
        "pkYVOm8953k:USC Law Speech 2007",
        "en:Charlie_Munger,zh:查理·芒格",
    ),
    (
        "peter_thiel",
        "彼得·提爾",
        "Peter Thiel",
        "PayPal Palantir",
        "Ro7enGnDOeE:Lex Fridman #285",
        "en:Peter_Thiel,en:Palantir",
    ),
    (
        "indra_nooyi",
        "英德拉·努伊",
        "Indra Nooyi",
        "PepsiCo",
        "",
        "en:Indra_Nooyi,en:PepsiCo",
    ),
    (
        "michael_porter",
        "麥可·波特",
        "Michael Porter",
        "Harvard strategy",
        "",
        "en:Michael_Porter,en:Competitive_advantage",
    ),
    (
        "sheryl_sandberg",
        "雪莉·桑德伯格",
        "Sheryl Sandberg",
        "Meta Facebook",
        "18uD6yPnoII:Lean In TED",
        "en:Sheryl_Sandberg,en:Meta_Platforms",
    ),
    (
        "terry_gou",
        "郭台銘",
        "Terry Gou",
        "Foxconn 鴻海",
        "",
        "zh:郭台铭,zh:鸿海精密,en:Terry_Gou,en:Foxconn",
    ),
]


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

    print("\n" + "=" * 60)
    print(">>> 向量化（全部新 chunks）")
    print("=" * 60)
    subprocess.run(
        [str(PY), str(ROOT / "rag" / "embed_chunks.py"), "--no-index"],
        cwd=ROOT,
        check=False,
    )

    print("\n=== 批次完成 ===")
    if failed:
        print("部分失敗 slug：", ", ".join(failed))
    print("統計 SQL（pgAdmin）：")
    print(
        "  SELECT p.slug, d.source_type, COUNT(*) FROM documents d"
        " JOIN persons p ON p.id=d.person_id"
        " GROUP BY p.slug, d.source_type ORDER BY p.slug;"
    )


if __name__ == "__main__":
    main()
