"""
用 yt-dlp 依關鍵字搜尋 YouTube 影片（不需 API Key）

  from youtube_discover import discover_videos
  videos = discover_videos("Sam Altman", name_zh="山姆·阿特曼", max_total=8)
"""

from __future__ import annotations

import time

import yt_dlp

SEARCH_DELAY_SEC = 1.0


def _ydl_opts() -> dict:
    return {
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "proxy": "",
        "socket_timeout": 30,
    }


def search_youtube(query: str, max_results: int = 5) -> list[tuple[str, str]]:
    """回傳 [(video_id, title), ...]"""
    opts = {
        **_ydl_opts(),
        "extract_flat": "in_playlist",
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)

    entries = info.get("entries") if info else None
    if not entries:
        return []

    out: list[tuple[str, str]] = []
    for entry in entries:
        if not entry:
            continue
        vid = entry.get("id") or ""
        if not vid and entry.get("url"):
            # 有時 id 在 url 裡
            url = entry["url"]
            if "v=" in url:
                vid = url.split("v=")[1].split("&")[0]
        title = (entry.get("title") or "").strip() or f"YouTube {vid}"
        if vid and len(vid) >= 11:
            out.append((vid[:11], title))
    return out


def discover_videos(
    name_en: str,
    *,
    name_zh: str = "",
    company: str = "",
    max_total: int = 8,
    per_query: int = 4,
) -> list[tuple[str, str]]:
    """依姓名組合搜尋詞，去重後回傳影片清單。"""
    queries: list[str] = []
    if name_en.strip():
        ne = name_en.strip()
        queries.extend(
            [
                f"{ne} interview",
                f"{ne} keynote speech",
                f"{ne} podcast full",
            ]
        )
        if company.strip():
            queries.append(f"{ne} {company.strip()} interview")
    if name_zh.strip():
        nz = name_zh.strip()
        queries.extend([f"{nz} 專訪", f"{nz} 演講"])

    # 去重搜尋詞
    seen_q: set[str] = set()
    unique_queries: list[str] = []
    for q in queries:
        if q not in seen_q:
            seen_q.add(q)
            unique_queries.append(q)

    seen_vid: set[str] = set()
    results: list[tuple[str, str]] = []

    for query in unique_queries:
        if len(results) >= max_total:
            break
        print(f"  YouTube 搜尋：{query}")
        try:
            found = search_youtube(query, max_results=per_query)
        except Exception as e:
            print(f"    ✗ 搜尋失敗：{e}")
            time.sleep(SEARCH_DELAY_SEC)
            continue

        for vid, title in found:
            if vid in seen_vid:
                continue
            seen_vid.add(vid)
            results.append((vid, title))
            short = title if len(title) <= 70 else title[:67] + "..."
            print(f"    → {vid} | {short}")
            if len(results) >= max_total:
                break
        time.sleep(SEARCH_DELAY_SEC)

    return results


def merge_video_lists(
    *lists: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """合併多組 (id, title)，手動指定的優先保留。"""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for lst in lists:
        for vid, title in lst:
            if vid in seen:
                continue
            seen.add(vid)
            out.append((vid, title))
    return out
