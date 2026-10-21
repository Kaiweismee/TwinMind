"""
演講爬蟲：YouTube 字幕 + 官方網頁全文

執行：
  cd ~/Desktop/digital_twin_project
  ./venv/bin/pip install -r requirements.txt
  ./venv/bin/python crawl/speech_fetch.py
"""

from __future__ import annotations

import re
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import psycopg2
import requests
import trafilatura
import yt_dlp
from psycopg2.extras import RealDictCursor
from requests import Session
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)

sys.path.insert(0, str(Path(__file__).parent))
from db_utils import DB_CONFIG, get_person_id, print_stats, save_document_and_chunks

HEADERS = {
    "User-Agent": "digital-twin-thesis-poc/1.0 (education; contact: local-dev)",
}

MIN_SPEECH_CHARS = 500
REQUEST_DELAY_SEC = 2.0

_youtube_api: YouTubeTranscriptApi | None = None


def get_youtube_api() -> YouTubeTranscriptApi:
    global _youtube_api
    if _youtube_api is None:
        session = Session()
        session.trust_env = False
        session.headers.update(HEADERS)
        _youtube_api = YouTubeTranscriptApi(http_client=session)
    return _youtube_api


@dataclass
class YouTubeSpeech:
    person_slug: str
    video_id: str
    title: str
    language: str
    lang_prefs: tuple[str, ...] = ("en", "en-US", "zh-Hant", "zh-TW", "zh")


@dataclass
class WebSpeech:
    person_slug: str
    url: str
    title: str
    language: str


YOUTUBE_SPEECHES = [
    # 黃仁勳 — GTC Keynote
    YouTubeSpeech("jensen_huang", "Y2F8yisiS6E", "GTC March 2024 Keynote (NVIDIA)", "en"),
    YouTubeSpeech("jensen_huang", "DiGB5uAYKAg", "GTC 2023 Keynote (NVIDIA)", "en"),
    YouTubeSpeech("jensen_huang", "39ubNuxnrK8", "GTC 2022 Spring Keynote (NVIDIA)", "en"),
    YouTubeSpeech("jensen_huang", "PWcNlRI00jo", "GTC Sept 2022 Keynote (NVIDIA)", "en"),
    # 馬斯克 — Tesla 公開活動
    YouTubeSpeech("elon_musk", "Hl1zEzVUV7w", "Tesla Investor Day 2023", "en"),
    YouTubeSpeech("elon_musk", "ODSJsviD_SU", "Tesla AI Day 2022", "en"),
    YouTubeSpeech("elon_musk", "j0z4FweCy4M", "Tesla AI Day 2021", "en"),
    # 賈伯斯 — 經典演講與公開訪談
    YouTubeSpeech("steve_jobs", "UF8uR6Z-2Yg", "Stanford Commencement 2005", "en"),
    YouTubeSpeech("steve_jobs", "iGE8X2MiCzM", "Steve Jobs introduces iPhone (2007)", "en"),
    YouTubeSpeech("steve_jobs", "ORpB8-NlWQ0", "Steve Jobs Interview 1995 (Lost Interview)", "en"),
    YouTubeSpeech("steve_jobs", "ftf4riVJHhw", "Steve Jobs at D8 Conference 2010", "en"),
    YouTubeSpeech("steve_jobs", "vgw7Akim58M", "Steve Jobs introduces Macintosh (1984)", "en"),
    # 蓋茲 — TED 與公開演講
    YouTubeSpeech("bill_gates", "SRrmOiIGBTg", "The next outbreak? We're not ready (TED 2015)", "en"),
    YouTubeSpeech("bill_gates", "FN2RM-CHkuI", "Innovating to zero! (TED 2010)", "en"),
    YouTubeSpeech("bill_gates", "8tfF9tNwolA", "Teachers need real feedback (TED)", "en"),
    YouTubeSpeech("bill_gates", "nLcNNDCW0VM", "Bill Gates on AI and the future (2024)", "en"),
    YouTubeSpeech("bill_gates", "6Af6b_wyiwI", "Bill Gates and Warren Buffett at Columbia (2017)", "en"),
    YouTubeSpeech("bill_gates", "CJEC0aAjRJE", "Bill Gates on GPT-4 vs GPT-5 (Lex Fridman clip)", "en"),
    # 吳恩達 — 訪談與公開演講
    YouTubeSpeech("andrew_ng", "0jspaMLxBig", "Lex Fridman Podcast #73 - Deep Learning & Education", "en"),
    YouTubeSpeech("andrew_ng", "jGwO-UgTSX4", "Andrew Ng - What is Machine Learning?", "en"),
    YouTubeSpeech("andrew_ng", "MniNHtKg270", "Andrew Ng - The State of AI (Stanford HAI)", "en"),
    YouTubeSpeech("jeff_bezos", "vKJr8kqRkaU", "Jeff Bezos Princeton 2010", "en"),
    YouTubeSpeech("ray_dalio", "U4s4RWmv8WI", "Ray Dalio - How to build a company", "en"),
    YouTubeSpeech("charlie_munger", "pkYVOm8953k", "Charlie Munger USC Law Speech 2007", "en"),
    YouTubeSpeech("peter_thiel", "Ro7enGnDOeE", "Peter Thiel - Lex Fridman #285", "en"),
    YouTubeSpeech("sheryl_sandberg", "18uD6yPnoII", "Sheryl Sandberg - Why so few women leaders", "en"),
    # 教育家／思想家（TED、演講）
    YouTubeSpeech("peter_drucker", "HhE2eCqdovw", "Peter Drucker: An Enduring Legacy", "en"),
    YouTubeSpeech("ken_robinson", "iG9C55XpBU", "Ken Robinson - Do schools kill creativity (TED)", "en"),
    YouTubeSpeech("ken_robinson", "r9KhyYYyETo", "Ken Robinson - Bring on the learning revolution (TED)", "en"),
    YouTubeSpeech("sal_khan", "gM95HHI4gLk", "Sal Khan - Let's use video to reinvent education (TED)", "en"),
    YouTubeSpeech("sugata_mitra", "BECNs71GHsA", "Sugata Mitra - School in the Cloud (TED)", "en"),
    YouTubeSpeech("carol_dweck", "J-swZaKN2Ic", "Carol Dweck - The power of yet (TEDx)", "en"),
    YouTubeSpeech("howard_gardner", "8N2pnYne0ZA", "Howard Gardner - Multiple intelligences (lecture)", "en"),
    YouTubeSpeech("howard_gardner", "IfzrN2yMBaQ", "Howard Gardner - Beyond Wit and Grit (TEDx)", "en"),
    # 歷史人物（紀錄片／演講字幕）
    YouTubeSpeech("albert_einstein", "mg8mqvOfXDI", "Albert Einstein interview 1955", "en"),
    YouTubeSpeech("winston_churchill", "jM3z14c3OSU", "Churchill - Blood Toil Tears and Sweat speech", "en"),
    YouTubeSpeech("nikola_tesla", "3J7bAZNGht8", "Nikola Tesla documentary excerpt", "en"),
    YouTubeSpeech("aristotle", "PrvtOWEXDIQ", "Crash Course Philosophy - Aristotle & Virtue", "en"),
    YouTubeSpeech("abraham_lincoln", "aAgX5wWM5X4", "Gettysburg Address (Lincoln)", "en"),
    YouTubeSpeech("marie_curie", "GGyLOi0EA0w", "Marie Curie biography documentary", "en"),
]

WEB_SPEECHES = [
    # 黃仁勳 — NVIDIA Blog
    WebSpeech(
        "jensen_huang",
        "https://blogs.nvidia.com/blog/gtc-2024-jensen-huang/",
        "GTC 2024 Keynote Highlights (NVIDIA Blog)",
        "en",
    ),
    WebSpeech(
        "jensen_huang",
        "https://blogs.nvidia.com/blog/2024-gtc-keynote/",
        "GTC 2024 Keynote Wrap-Up (NVIDIA Blog)",
        "en",
    ),
    WebSpeech(
        "jensen_huang",
        "https://blogs.nvidia.com/blog/gtc-keynote-spring-2023/",
        "GTC 2023 Keynote Wrap-Up (NVIDIA Blog)",
        "en",
    ),
    WebSpeech(
        "jensen_huang",
        "https://blogs.nvidia.com/blog/nvidia-ceo-jensen-huang-ai-factory-generative-ai/",
        "NVIDIA CEO on AI Factory (NVIDIA Blog)",
        "en",
    ),
    WebSpeech(
        "jensen_huang",
        "https://blogs.nvidia.com/blog/gtc-2024-transformer-ai-research-panel-jensen/",
        "GTC 2024 Transformer Panel with Jensen (NVIDIA Blog)",
        "en",
    ),
    # 馬斯克 — Tesla 官方頁
    WebSpeech(
        "elon_musk",
        "https://www.tesla.com/AI",
        "Tesla AI (Official Page)",
        "en",
    ),
    WebSpeech(
        "elon_musk",
        "https://www.tesla.com/master-plan-part-4",
        "Tesla Master Plan Part 4",
        "en",
    ),
    WebSpeech(
        "steve_jobs",
        "https://www.apple.com/newsroom/",
        "Apple Newsroom (archives)",
        "en",
    ),
    WebSpeech(
        "bill_gates",
        "https://www.gatesnotes.com/",
        "Gates Notes (official blog)",
        "en",
    ),
    # Stanford Encyclopedia（長文，適合歷史人物 RAG）
    WebSpeech(
        "confucius",
        "https://plato.stanford.edu/entries/confucius/",
        "Stanford Encyclopedia - Confucius",
        "en",
    ),
    WebSpeech(
        "john_dewey",
        "https://plato.stanford.edu/entries/dewey/",
        "Stanford Encyclopedia - John Dewey",
        "en",
    ),
    WebSpeech(
        "paulo_freire",
        "https://iep.utm.edu/freire/",
        "Internet Encyclopedia of Philosophy - Paulo Freire",
        "en",
    ),
    WebSpeech(
        "maria_montessori",
        "http://www.montessori.edu/maria.html",
        "Montessori.edu - Maria Montessori biography",
        "en",
    ),
    WebSpeech(
        "aristotle",
        "https://plato.stanford.edu/entries/aristotle/",
        "Stanford Encyclopedia - Aristotle",
        "en",
    ),
    WebSpeech(
        "albert_einstein",
        "https://www.nobelprize.org/prizes/physics/1921/einstein/biographical/",
        "Nobel Prize - Albert Einstein biographical",
        "en",
    ),
    WebSpeech(
        "marie_curie",
        "https://www.nobelprize.org/prizes/physics/1903/marie-curie/biographical/",
        "Nobel Prize - Marie Curie biographical",
        "en",
    ),
    WebSpeech(
        "sun_tzu",
        "https://plato.stanford.edu/entries/school-names-chinese/",
        "Stanford Encyclopedia - Chinese philosophy (Sun Tzu context)",
        "en",
    ),
]


def fetch_youtube_transcript_api(speech: YouTubeSpeech) -> str | None:
    """youtube-transcript-api 1.x：使用 api.fetch()"""
    try:
        transcript = get_youtube_api().fetch(
            speech.video_id, languages=speech.lang_prefs
        )
        text = " ".join(snippet.text for snippet in transcript.snippets)
        return " ".join(text.split())
    except (TranscriptsDisabled, VideoUnavailable, NoTranscriptFound, CouldNotRetrieveTranscript) as e:
        print(f"    API 字幕不可用：{e}")
        return None
    except AttributeError as e:
        print(f"    API 版本錯誤（請 pip install -U youtube-transcript-api）：{e}")
        return None
    except Exception as e:
        print(f"    API 讀取失敗：{e}")
        return None


def parse_vtt(vtt_text: str) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for raw in vtt_text.splitlines():
        line = re.sub(r"<[^>]+>", "", raw.strip())
        if not line or line == "WEBVTT" or "-->" in line or line.isdigit():
            continue
        if line.startswith("NOTE") or line.startswith("STYLE"):
            continue
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)
    return " ".join(lines)


def fetch_youtube_transcript_ytdlp(speech: YouTubeSpeech) -> str | None:
    """備援：yt-dlp 下載自動字幕"""
    url = f"https://www.youtube.com/watch?v={speech.video_id}"
    with tempfile.TemporaryDirectory() as tmp:
        out = str(Path(tmp) / speech.video_id)
        ydl_opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": list(speech.lang_prefs),
            "subtitlesformat": "vtt/best",
            "outtmpl": out,
            "quiet": True,
            "no_warnings": True,
            "nocheckcertificate": True,
            "proxy": "",
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            print(f"    yt-dlp 失敗：{e}")
            return None

        vtt_files = sorted(Path(tmp).glob("*.vtt"))
        if not vtt_files:
            print("    yt-dlp：找不到字幕檔")
            return None

        text = parse_vtt(vtt_files[0].read_text(encoding="utf-8", errors="ignore"))
        return " ".join(text.split()) if text else None


def fetch_youtube_transcript(speech: YouTubeSpeech) -> tuple[str | None, str]:
    text = fetch_youtube_transcript_api(speech)
    if text and len(text) >= MIN_SPEECH_CHARS:
        return text, "youtube_transcript_api"

    print("    嘗試 yt-dlp 備援字幕…")
    text = fetch_youtube_transcript_ytdlp(speech)
    if text and len(text) >= MIN_SPEECH_CHARS:
        return text, "yt-dlp_vtt"
    return None, ""


def fetch_web_article(page: WebSpeech) -> str | None:
    with requests.Session() as session:
        session.trust_env = False
        session.headers.update(HEADERS)
        resp = session.get(page.url, timeout=30)
    resp.raise_for_status()
    text = trafilatura.extract(resp.text, url=page.url, include_comments=False)
    if not text:
        return None
    return " ".join(text.split())


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
    print("=== 演講爬蟲（YouTube + 網頁，已修復 API 1.x）===\n")
    youtube_list = YOUTUBE_SPEECHES
    web_list = WEB_SPEECHES
    if person_slug:
        youtube_list = [s for s in YOUTUBE_SPEECHES if s.person_slug == person_slug]
        web_list = [w for w in WEB_SPEECHES if w.person_slug == person_slug]

    conn = psycopg2.connect(**DB_CONFIG)
    ok, skip, fail = 0, 0, 0

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            print("【YouTube 演講字幕】")
            for speech in youtube_list:
                source_url = f"https://www.youtube.com/watch?v={speech.video_id}"
                print(f"  {speech.person_slug}: {speech.title}")
                text, method = fetch_youtube_transcript(speech)
                time.sleep(REQUEST_DELAY_SEC)

                if not text:
                    print("    → 跳過（無字幕）\n")
                    skip += 1
                    continue

                person_id = get_person_id(cur, speech.person_slug)
                doc_id, n_chunks = save_document_and_chunks(
                    cur,
                    person_id=person_id,
                    source_url=source_url,
                    title=speech.title,
                    raw_content=text,
                    language=speech.language,
                    source_type="speech",
                    metadata={
                        "source": method,
                        "video_id": speech.video_id,
                        "chars": len(text),
                    },
                )
                conn.commit()
                ok += 1
                print(f"    → ✓ [{method}] doc_id={doc_id}, {len(text)} 字, {n_chunks} chunks\n")

            print("【網頁演講 / 官方文章】")
            for page in web_list:
                print(f"  {page.person_slug}: {page.title}")
                try:
                    text = fetch_web_article(page)
                    time.sleep(REQUEST_DELAY_SEC)
                except requests.RequestException as e:
                    print(f"    → ✗ 下載失敗：{e}\n")
                    fail += 1
                    continue

                if not text or len(text) < MIN_SPEECH_CHARS:
                    print("    → 跳過（內容太短）\n")
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
                    source_type="speech",
                    metadata={"source": "trafilatura_web", "chars": len(text)},
                )
                conn.commit()
                ok += 1
                print(f"    → ✓ doc_id={doc_id}, {len(text)} 字, {n_chunks} chunks\n")

        print(f"本輪：成功 {ok} 篇，跳過 {skip} 篇，失敗 {fail} 篇\n")
        print_stats(conn)
        print()
        print_stats_by_type(conn)
    finally:
        conn.close()

    print("\n完成。pgAdmin：SELECT title, LENGTH(raw_content) FROM documents WHERE source_type='speech';")


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--person", help="只抓此人，例如 steve_jobs")
    args = p.parse_args()
    main(person_slug=args.person)
