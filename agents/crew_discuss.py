"""
數位分身討論：CrewAI + RAG（馬斯克 vs 黃仁勳）

使用前：
  1. 複製 .env.example 為 .env，填入 OPENAI_API_KEY
  2. pip install -r requirements.txt

執行：
  cd ~/Desktop/digital_twin_project
  ./venv/bin/python agents/crew_discuss.py --topic "AI 的未來十年會如何改變產業？"
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

sys.path.insert(0, str(PROJECT_ROOT / "rag"))
sys.path.insert(0, str(Path(__file__).parent))

from crewai import Agent, Crew, LLM, Process, Task

from db_chat import add_message, create_session, end_session
from rag_context import retrieve_for_person


def _require_api_key() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit(
            "請在 .env 設定 OPENAI_API_KEY（可複製 .env.example）"
        )


def _llm() -> LLM:
    # OPENAI_API_KEY 由 .env 載入至環境變數
    return LLM(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.7,
    )


def build_agents(llm: LLM) -> dict[str, Agent]:
    return {
        "moderator": Agent(
            role="討論主持人",
            goal="引導馬斯克與黃仁勳就有關 AI 與科技的議題進行有深度的對話，並做簡潔總結。",
            backstory=(
                "你是專業科技論壇主持人，中立、清晰，擅長提出好問題與收束重點。"
                "使用繁體中文。"
            ),
            llm=llm,
            verbose=True,
        ),
        "musk": Agent(
            role="伊隆·馬斯克",
            goal="以馬斯克的視角與語氣參與討論，並依據提供的資料發言。",
            backstory=(
                "你是伊隆·馬斯克：直接、敢說、常談第一原理、火星、Tesla、SpaceX、AI 風險與創新。"
                "發言可中英夾雜，但主要用繁體中文。只根據【參考資料】論述；資料不足時說「我不確定」。"
            ),
            llm=llm,
            verbose=True,
        ),
        "jensen": Agent(
            role="黃仁勳",
            goal="以黃仁勳的視角與語氣參與討論，並依據提供的資料發言。",
            backstory=(
                "你是 NVIDIA 執行長黃仁勳：談加速運算、GPU、AI 基礎建設、生態系與產業趨勢。"
                "用繁體中文，務實、有技術深度。只根據【參考資料】論述；資料不足時說「我不確定」。"
            ),
            llm=llm,
            verbose=True,
        ),
    }


def run_discussion(topic: str, top_k: int = 5) -> int:
    _require_api_key()
    llm = _llm()
    agents = build_agents(llm)

    print("正在 RAG 檢索…")
    musk_ctx, musk_ids, _ = retrieve_for_person("elon_musk", topic, top_k=top_k)
    jensen_ctx, jensen_ids, _ = retrieve_for_person("jensen_huang", topic, top_k=top_k)
    print(f"  馬斯克：{len(musk_ids)} 段｜黃仁勳：{len(jensen_ids)} 段\n")

    session_id = create_session(topic)

    # 任務與 (role, chunk_ids) 對應，方便寫入資料庫
    task_open = Task(
        description=(
            f"討論題目：{topic}\n\n"
            "請用 2～3 句話開場，說明議題重要性，並邀請兩位來賓發表看法。"
        ),
        expected_output="主持人開場白，繁體中文，約 80～150 字。",
        agent=agents["moderator"],
    )

    task_musk_1 = Task(
        description=(
            f"討論題目：{topic}\n\n"
            f"【你的參考資料】\n{musk_ctx}\n\n"
            "請以伊隆·馬斯克身份發表第一段看法（約 120～200 字），"
            "需引用或呼應參考資料中的觀點，不要捏造未出現的具體數字或引語。"
        ),
        expected_output="馬斯克的第一輪發言。",
        agent=agents["musk"],
    )

    task_jensen_1 = Task(
        description=(
            f"討論題目：{topic}\n\n"
            f"【你的參考資料】\n{jensen_ctx}\n\n"
            "請以黃仁勳身份回應馬斯克的觀點，並提出你的角度（約 120～200 字）。"
            "需基於參考資料，可同意或補充不同觀點。"
        ),
        expected_output="黃仁勳的第一輪發言。",
        agent=agents["jensen"],
    )

    task_musk_2 = Task(
        description=(
            f"針對題目與黃仁勳的發言，以馬斯克身份再回應一輪（約 100～180 字）。\n\n"
            f"【參考資料】\n{musk_ctx}"
        ),
        expected_output="馬斯克的第二輪發言。",
        agent=agents["musk"],
    )

    task_jensen_2 = Task(
        description=(
            f"針對題目與馬斯克的發言，以黃仁勳身份再回應一輪（約 100～180 字）。\n\n"
            f"【參考資料】\n{jensen_ctx}"
        ),
        expected_output="黃仁勳的第二輪發言。",
        agent=agents["jensen"],
    )

    task_close = Task(
        description=(
            f"題目：{topic}\n\n"
            "請總結雙方 2 輪討論的共識與分歧，各 1～2 點，並作結語（約 120～180 字）。"
        ),
        expected_output="主持人總結。",
        agent=agents["moderator"],
    )

    tasks = [task_open, task_musk_1, task_jensen_1, task_musk_2, task_jensen_2, task_close]
    meta = [
        ("moderator", []),
        ("musk", musk_ids),
        ("jensen", jensen_ids),
        ("musk", musk_ids),
        ("jensen", jensen_ids),
        ("moderator", []),
    ]

    crew = Crew(
        agents=list(agents.values()),
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )

    print("=== 開始 CrewAI 討論 ===\n")
    result = crew.kickoff()

    print("\n=== 討論紀錄 ===\n")
    for task, (role, chunk_ids) in zip(tasks, meta):
        text = ""
        if task.output:
            text = str(task.output.raw) if hasattr(task.output, "raw") else str(task.output)
        text = text.strip()
        if text:
            label = {"musk": "伊隆·馬斯克", "jensen": "黃仁勳", "moderator": "主持人"}[role]
            print(f"【{label}】\n{text}\n")
            add_message(session_id, role, text, chunk_ids=chunk_ids)

    summary = str(result).strip() if result else ""
    end_session(session_id, summary=summary[:2000] if summary else None)

    print(f"已寫入資料庫 chat_sessions.id = {session_id}")
    print("pgAdmin：SELECT * FROM chat_messages WHERE session_id =", session_id)
    return session_id


def main() -> None:
    parser = argparse.ArgumentParser(description="數位分身 CrewAI 討論")
    parser.add_argument(
        "--topic",
        required=True,
        help="討論題目，例如：AI 監管應如何平衡創新與安全？",
    )
    parser.add_argument("--top-k", type=int, default=5, help="RAG 每人检索几段")
    args = parser.parse_args()
    run_discussion(args.topic, top_k=args.top_k)


if __name__ == "__main__":
    main()
