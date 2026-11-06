"""
多人討論：一次一則發言；名人回覆須在句尾標註 [1][2] 對應參考資料。
"""

from __future__ import annotations

import os
import random
import re
from dataclasses import dataclass
from typing import Any

from web.core.rag_backend import format_context, search_chunks

from web.repositories import chat_store

CITE_MARKER_RE = re.compile(r"\[(\d+|推論)\]|【(\d+|推論)】")
CITE_RE = re.compile(
    r"([^[\]【】]+?)((?:\[(?:\d+|推論)\]|【(?:\d+|推論)】)"
    r"(?:[ \t]*(?:\[(?:\d+|推論)\]|【(?:\d+|推論)】))*)"
)


def _normalize_cite_markers(text: str) -> str:
    """將全形【1】【推論】統一成半形，方便解析與前端一致。"""
    t = re.sub(r"【(\d+)】", r"[\1]", text or "")
    return t.replace("【推論】", "[推論]")


@dataclass
class TurnSpec:
    kind: str  # user_twin | celeb | conclusion
    phase: str  # opening | debate | conclusion
    member: dict[str, Any] | None = None


def _format_transcript(
    messages: list[dict[str, Any]],
    user_name: str,
    *,
    exclude_roles: set[str] | None = None,
) -> str:
    exclude_roles = exclude_roles or set()
    lines: list[str] = []
    for m in messages:
        role = m.get("role")
        if role in exclude_roles:
            continue
        if role == "user":
            lines.append(f"{user_name}：{m['content']}")
        elif role == "user_twin":
            lines.append(f"{user_name}（分身）：{m['content']}")
        elif role == "conclusion":
            continue
        else:
            name = m.get("person_name_zh") or role
            lines.append(f"{name}：{m['content']}")
    return "\n".join(lines)


def _sources_payload(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in results:
        text = r.get("content") or ""
        if len(text) > 2800:
            text = text[:2800] + "…"
        out.append({
            "chunk_id": int(r["chunk_id"]),
            "similarity": round(float(r["similarity"]), 4),
            "title": r.get("title"),
            "source_type": r.get("source_type"),
            "source_url": r.get("source_url"),
            "content": text,
        })
    return out


def _pack_sources(sources: list[dict[str, Any]], segments: list[dict[str, Any]]) -> Any:
    if not segments:
        return sources
    return {"sources": sources, "segments": segments}


def _unpack_sources(raw: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if isinstance(raw, dict) and "sources" in raw:
        return list(raw.get("sources") or []), list(raw.get("segments") or [])
    if isinstance(raw, list):
        return raw, []
    return [], []


def parse_cited_reply(raw: str, sources: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """
    解析「……可能被取代[2]，但這也……[1]」→ 顯示文字 + 逐句引用。
    source_refs 為 1-based，對應本則訊息的 sources 列表。
    """
    text = _normalize_cite_markers((raw or "").strip())
    if not text:
        return "", []

    segments: list[dict[str, Any]] = []
    last = 0
    display_parts: list[str] = []

    for m in CITE_RE.finditer(text):
        before = text[last : m.start()].strip()
        if before:
            display_parts.append(before)
            segments.append({
                "text": before,
                "source_refs": [],
                "chunk_ids": [],
                "inference": True,
            })

        clause = m.group(1).strip()
        markers = [
            marker.group(1) or marker.group(2)
            for marker in CITE_MARKER_RE.finditer(m.group(2))
        ]
        refs = [int(marker) for marker in markers if marker.isdigit()]
        refs = [idx for idx in refs if 1 <= idx <= len(sources)]
        if not clause:
            last = m.end()
            continue

        display_parts.append(clause)
        if refs:
            # 上傳文件的頁面引用有真實檔案來源，但不一定對應向量 chunk。
            chunk_ids = [
                int(sources[idx - 1]["chunk_id"]) for idx in refs
                if sources[idx - 1].get("chunk_id") is not None
            ]
            segments.append({
                "text": clause,
                "source_refs": refs,
                "chunk_ids": chunk_ids,
                "inference": "推論" in markers,
            })
        else:
            segments.append({
                "text": clause,
                "source_refs": [],
                "chunk_ids": [],
                "inference": True,
            })
        last = m.end()

    tail = text[last:].strip()
    if tail:
        display_parts.append(tail)
        segments.append({
            "text": tail,
            "source_refs": [],
            "chunk_ids": [],
            "inference": True,
        })

    if not segments:
        return text, [{
            "text": text,
            "source_refs": [],
            "chunk_ids": [],
            "inference": True,
        }]

    display = "".join(display_parts) if display_parts else text
    return display, segments


def _rag_context(person_slug: str, query: str, top_k: int) -> tuple[str, list[int], list[dict]]:
    results = search_chunks(query, person_slug=person_slug, top_k=top_k)
    context = format_context(results)
    if not context.strip():
        context = "（知識庫未檢索到相關資料）"
    chunk_ids = [int(r["chunk_id"]) for r in results]
    return context, chunk_ids, _sources_payload(results)


def _append_session_context(
    context: str,
    chunk_ids: list[int],
    sources: list[dict],
    *,
    user_id: int | None,
    session_id: int,
    query: str,
    top_k: int,
    persona_first: bool = False,
) -> tuple[str, list[int], list[dict]]:
    if persona_first:
        persona_context = format_context(sources) if sources else context
        persona_block = f"【分身個人資料｜主要依據】\n{persona_context}"
    if not user_id or not session_id:
        if persona_first:
            return persona_block, chunk_ids, sources
        return context, chunk_ids, sources
    from web.knowledge import user_rag

    sess_ctx, sess_ids, sess_src = user_rag.search_session_context(
        user_id,
        session_id,
        query,
        top_k=min(2, top_k) if persona_first else min(6, top_k),
    )
    if not sess_ctx.strip():
        if persona_first:
            return persona_block, chunk_ids, sources
        return context, chunk_ids, sources
    if persona_first:
        # 附件只交代情境，不加入此分身可引用的 sources，確保 [n] 只指向個人資料。
        session_context = "\n\n".join(
            re.sub(r"\[\d+\]|【\d+】", "", f"{s.get('title') or '背景資料'}\n{s.get('content') or ''}")
            for s in sess_src
        )
        merged = (
            f"{persona_block}\n\n"
            f"【房主提供的情境背景｜沒有引用編號】\n{session_context}"
        )
        return merged, chunk_ids, sources

    # 房主資料先出現在提示詞與 sources；名人資料編號需接續其後，才能讓 [n] 對到相同來源。
    personal_context = (
        format_context(sources, start_index=len(sess_src) + 1)
        if sources
        else ""
    )
    merged = (
        f"【房主提供的參考資料】\n{sess_ctx}\n\n【你的參考資料】\n{personal_context}"
        if personal_context.strip()
        else f"【房主提供的參考資料】\n{sess_ctx}"
    )
    return merged, sess_ids + chunk_ids, sess_src + sources


def _llm(client: Any, model: str, system: str, user: str, temperature: float = 0.7) -> str:
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return (resp.choices[0].message.content or "").strip()


def _discussion_brief(topic: str, extra: str = "") -> str:
    brief = extra.strip() if extra.strip() else f"我們要討論的主題是：{topic}"
    if _is_innoserve_award_topic(topic):
        brief += _INNOSERVE_PROJECT_CONTEXT + _INNOSERVE_SCORING_CONTEXT + _INNOSERVE_DEMO_GUIDE
    return brief


def _is_innoserve_award_topic(topic: str) -> bool:
    normalized = re.sub(r"[\W_]+", "", (topic or "").casefold())
    has_award_intent = any(
        word in normalized for word in ("得名", "得獎", "獲獎", "獲名次", "拿名次")
    )
    return any(name in normalized for name in ("innoserve", "分身有術")) and has_award_intent


# 來源：房主提供的《分身有術企劃書（最終版）》第 3–4、10–11、26、30–31 頁。
_INNOSERVE_PROJECT_CONTEXT = """

【房主提供的專題背景｜分身有術】
本次參賽作品是「分身有術——數位分身討論系統」，參加 InnoServe 大專校院資訊應用服務創新競賽的資訊應用組（IP）。本場核心問題是：這個作品如何改善內容與展示，爭取在資訊應用組得名？
問題與動機：團隊成員思考角度相似，容易忽略重要問題；反覆討論卻難以收斂，事後也難以追查判斷依據與意見演變。
目標使用者：大學生與研究人員、新創團隊、數位轉型企業及自學者。希望協助他們比較不同觀點、發現盲點、理解討論脈絡並形成較清楚的決策。
專題核心功能：
1. 多角色討論：使用者選擇不同思考風格的數位分身，與自己的分身共同討論；其他使用者可透過加入碼參與。
2. 個人數位分身：透過持續對話與上傳檔案建立個人知識背景，支援學習、工作等不同情境。
3. 檢索與引用：以 RAG 搭配 PostgreSQL／pgvector，檢索相關資料再生成回覆；聊天室提供可點擊的引用，讓使用者查看回答依據。
4. 視覺化討論：以心智圖呈現議題與人物觀點，並以討論路徑／立場變化輔助理解討論過程。
作品的價值主張：把個人背景、多角色觀點、可追查依據與視覺化討論串在一起，協助使用者理解「如何形成判斷」。上述使用效益以設計目標表達，不編造改善比例、測試紀錄或成效。
企劃書的未來方向包含更即時的圖譜更新、深化結論整合與語音互動；語音屬未來規劃。結論整合與圖譜能力請依本場系統實際提供的功能描述，不將企劃書中的舊版限制當成現況。
這是房主提供的作品背景，不是名人的個人資料，也不使用名人的引用編號標註。名人仍應從自己的資料提出原則、例證與理由，再針對這個作品給建議。
"""


_INNOSERVE_IP_CRITERIA = (
    ("創新性", "創新度、影響力、整合性等", 30),
    ("實用性", "有效性、整合性等", 15),
    ("穩定性", "完整度、使用者體驗等", 15),
    ("擴充性", "延展性等", 15),
    ("系統文件完整性", "完整度、主題符合度、問題定義等", 15),
    ("說明展示表達能力", "", 10),
)

_INNOSERVE_SCORING_CONTEXT = (
    "\n\n【房主提供的資訊應用組（IP）評分標準】\n"
    + "\n".join(
        f"- {name}：{weight}%" + (f"（包含{details}）" if details else "")
        for name, details, weight in _INNOSERVE_IP_CRITERIA
    )
    + "\n以上六項合計 100%。這是本場共同背景，不是名人個人資料，不使用名人的引用編號標註這些權重。\n"
)


_INNOSERVE_DEMO_GUIDE = """

【InnoServe 討論預設方向】
本場要從各分身的個人資料與專業觀點，討論「分身有術」如何提升作品價值、回答可信度與決策品質。
請聚焦三個面向：
1. 檢索引用與回答可信度：名人分身根據自己的個人知識資料與專業觀點回答，可點擊的 [1][2] 只引用自己的資料。InnoServe 規章和「分身有術」附件僅交代背景，由房主分身介紹；選擇有依據的內容說明，延伸做法用建議語氣表達，不要編造依據。
2. 公平呈現與視覺化：討論如何呈現多元角色、不同立場與觀點變化，提出檢查觀點涵蓋範圍與資料缺漏的具體做法。
3. 決策流程與使用價值：討論資料、不同觀點、心智圖與結論如何協助使用者理解問題、比較選項並做決定。
這三個面向是起點；若個人資料還支持使用者需求、產品價值、成效驗證或展示溝通等相關議題，可以提出不同的實質觀點，不必每輪重複這三項。

各分身請選擇自己資料最有依據的角度，說明相關知識、例證與理由，再連結本場主題，不必輪流覆述系統功能或操作步驟。
請將有關的建議自然連結到上述評分項目，說明能改善什麼、需要什麼實際證據。創新性占 30%，其餘項目也應視討論內容納入；每次發言不必重述六項標準或百分比，不推算沒有依據的得分。
若提及預先設定的人物推薦，請如實稱為預設推薦，不要描述成系統即時算出的排名。
"""


_DISCUSSION_RESPONSE_STYLE = (
    "【表達方式】直接提出與主題相關的觀點、具體理由與可執行建議。"
    "不要主動加入關於 AI 模擬身分、真人背書、得名機率或保證公平的制式聲明，"
    "也不要複述先前紀錄中的這類聲明。"
    "不要每輪檢查或附帶評論房主作品是否已有成效測試、壓力測試或迭代紀錄，"
    "也不要加上『個人資料並未證明這些做法必然帶來名次』、"
    "『目前提供的資料沒有本作品提升決策品質的測試結果』、"
    "『現有資料未提供，建議以實測補足』等制式補充，或換句話說同樣的內容。"
    "直接敘述資料支持的觀點與具體建議；若建議測試，直接說測試什麼、如何做或有什麼用途，"
    "不先加一段作品缺乏證據的聲明，也不複述歷史發言中的這類補充。"
    "若使用者明確詢問作品是否完成測試、實際成效、得名保證或要求查證，仍須據實回答；"
    "回答問題必需的未知或限制應簡短交代，不把未知說成已證實。"
    "延伸建議用建議語氣表達，具體事實仍須有依據，不將未驗證的成效寫成事實。"
)


_INNOSERVE_PERSONAL_RAG_HINT = (
    "技術創新、產品價值、資料可信度、引用驗證、公平呈現、視覺化、"
    "決策品質、使用者需求、問題解決；請從這個分身自己的專業知識與既有資料找相關內容。"
)


_CITE_RULE = (
    "【引用規則】你的發言會附編號參考資料，請用半形方括號 [1][2]（勿用【1】）。"
    "每一句或每一小段論述結尾，必須標註其依據：有資料則標 [編號]（如 ……可能被取代[2]）；"
    "資料未涵蓋的具體事實不要斷言；延伸分析與做法用看法或建議語氣表達，不強制附加資料不足聲明。"
    "不要加 [推論] 或其他不能點擊的標籤，也不可編造引用；不要為了讓發言看起來有依據而勉強引用。"
)


def _member_debate_rounds(m: dict[str, Any]) -> int:
    dr = m.get("debate_rounds")
    if dr is not None:
        return max(0, min(6, int(dr)))
    from web.recommendations.topic_fit import debate_rounds_from_fit

    return debate_rounds_from_fit(int(m.get("topic_fit_score") or 50))


def _fit_engagement_hint(topic_fit_score: int | None, phase: str) -> str:
    """依契合度要求發言深度（高契合多講、低契合少講）。"""
    score = 50 if topic_fit_score is None else int(topic_fit_score)
    if phase == "opening":
        if score >= 78:
            return (
                "【契合度：高】你是本主題的核心與會者，請充分展開立場、"
                "引用資料中的具體內容，並點出 2～3 個關鍵論點。"
            )
        if score >= 52:
            return "【契合度：中】請提出與主題相關的觀點，並簡要說明理由。"
        return "【契合度：低】簡短開場即可，避免過度延伸與主題無關的內容。"
    if score >= 78:
        return (
            "【契合度：高】請深入辯論：回應先前發言、提出反駁或補充例證，"
            "盡量引用資料；你是本輪應發言最多的專家之一。"
        )
    if score >= 52:
        return "【契合度：中】請回應他人觀點並補充你的看法，保持聚焦主題。"
    return "【契合度：低】簡短回應即可，勿長篇發揮。"


def _rag_top_k_for_fit(
    topic_fit_score: int | None,
    base: int,
    *,
    richer_personal_context: bool = False,
) -> int:
    score = 50 if topic_fit_score is None else int(topic_fit_score)
    if richer_personal_context:
        if score >= 78:
            return min(base + 10, 20)
        if score >= 52:
            return min(base + 6, 16)
        return max(6, base)
    if score >= 78:
        return min(base + 8, 24)
    if score >= 52:
        return min(base + 4, 16)
    return max(4, base - 2)


def _members_by_fit(members: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        members,
        key=lambda x: (
            -(x.get("topic_fit_score") if x.get("topic_fit_score") is not None else 50),
            x.get("sort_order", 0),
        ),
    )


def build_turn_queue(
    members: list[dict[str, Any]],
    *,
    include_user_twin: bool = True,
    include_debate: bool = True,
    include_conclusion: bool = True,
) -> list[TurnSpec]:
    """開場人人有份；辯論至少 3 輪、高契合最多 4 輪，高契合先發言。"""
    queue: list[TurnSpec] = []
    ordered = _members_by_fit(members)
    if include_user_twin:
        queue.append(TurnSpec("user_twin", "opening", None))
    for m in ordered:
        queue.append(TurnSpec("celeb", "opening", m))
    if include_debate and len(members) >= 1:
        min_global = int(os.getenv("CHAT_MIN_DEBATE_ROUNDS", "3"))
        max_rounds = max((_member_debate_rounds(m) for m in members), default=0)
        max_rounds = max(max_rounds, min_global)
        for round_i in range(max_rounds):
            for m in ordered:
                if round_i < _member_debate_rounds(m):
                    queue.append(TurnSpec("celeb", "debate", m))
        if include_user_twin:
            queue.append(TurnSpec("user_twin", "debate", None))
    if include_conclusion:
        queue.append(TurnSpec("conclusion", "conclusion", None))
    return queue


def _assistant_turn_count(messages: list[dict[str, Any]]) -> int:
    n = 0
    for m in messages:
        if m.get("role") in ("user", "conclusion"):
            continue
        n += 1
    return n


def get_next_turn(
    messages: list[dict[str, Any]],
    members: list[dict[str, Any]],
    *,
    include_user_twin: bool = True,
) -> TurnSpec | None:
    if any(m.get("role") == "conclusion" for m in messages):
        return None
    queue = build_turn_queue(members, include_user_twin=include_user_twin)
    idx = _assistant_turn_count(messages)
    if idx >= len(queue):
        return None
    return queue[idx]


def peek_next_turn_label(
    messages: list[dict[str, Any]],
    members: list[dict[str, Any]],
    user_name: str,
    *,
    include_user_twin: bool = True,
) -> str | None:
    speaker = peek_next_speaker(
        messages, members, user_name, include_user_twin=include_user_twin
    )
    if not speaker:
        return None
    if speaker["kind"] == "conclusion":
        return "產出討論結論"
    if speaker["kind"] == "user_twin":
        return f"請 {user_name}（分身）發言"
    if speaker["kind"] == "celeb":
        phase_zh = "開場" if speaker.get("phase") == "opening" else "回應"
        return f"請 {speaker['name_zh']} {phase_zh}"
    return "下一位發言"


def _is_demo_suggestion_turn(
    topic: str,
    messages: list[dict[str, Any]],
    members: list[dict[str, Any]],
    *,
    include_user_twin: bool = True,
) -> bool:
    """以既有發言佇列指定一次：第一位進入討論的名人提出展示建議。"""
    if not _is_innoserve_award_topic(topic):
        return False
    queue = build_turn_queue(members, include_user_twin=include_user_twin)
    demo_index = next(
        (i for i, turn in enumerate(queue) if turn.kind == "celeb" and turn.phase == "debate"),
        None,
    )
    if demo_index is None:
        demo_index = next(
            (i for i in reversed(range(len(queue))) if queue[i].kind == "celeb"),
            None,
        )
    return demo_index is not None and _assistant_turn_count(messages) == demo_index


def peek_next_speaker(
    messages: list[dict[str, Any]],
    members: list[dict[str, Any]],
    user_name: str,
    *,
    user_avatar_url: str = "",
    include_user_twin: bool = True,
) -> dict[str, Any] | None:
    spec = get_next_turn(messages, members, include_user_twin=include_user_twin)
    if not spec:
        return None
    if spec.kind == "conclusion":
        return {
            "kind": "conclusion",
            "name_zh": "討論結論",
            "person_slug": None,
            "avatar_url": None,
            "phase": "conclusion",
        }
    if spec.kind == "user_twin":
        return {
            "kind": "user_twin",
            "name_zh": f"{user_name}（分身）",
            "person_slug": None,
            "avatar_url": user_avatar_url,
            "phase": spec.phase,
        }
    if spec.member:
        m = spec.member
        return {
            "kind": "celeb",
            "name_zh": m["name_zh"],
            "person_slug": m["person_slug"],
            "avatar_url": m.get("avatar_url") or "",
            "phase": spec.phase,
        }
    return None


def _format_user_note(
    content: str,
    reply_to: str | None,
    members: list[dict[str, Any]],
    user_name: str,
) -> str:
    text = (content or "").strip()
    if not text:
        return ""
    target = (reply_to or "all").strip() or "all"
    if target == "all":
        return text
    if target == "user_twin":
        return f"（指定對象：{user_name}的分身）{text}"
    for m in members:
        slug = m.get("person_slug") or ""
        if slug == target:
            name = m.get("name_zh") or slug
            return f"（指定對象：{name}）{text}"
    return text


def _latest_user_note(
    messages: list[dict[str, Any]],
    members: list[dict[str, Any]],
    user_name: str,
) -> str:
    for m in reversed(messages):
        if m.get("role") == "user":
            return _format_user_note(
                str(m.get("content") or ""),
                m.get("reply_to"),
                members,
                user_name,
            )
    return ""


def _reply_innoserve_opening(
    client: Any, model: str, *, user_name: str, topic: str,
    discussion_brief: str, user_id: int, session_id: int,
) -> tuple[str, list[int], list[dict[str, Any]]]:
    from web.knowledge.user_rag import innoserve_opening_sources

    sources = innoserve_opening_sources(user_id, session_id)
    refs = {s["reference_kind"]: i for i, s in enumerate(sources, 1)}
    kinds = ("project_intro", "project_audience", "project_features", "project_citations", "competition_scoring")
    if not all(kind in refs for kind in kinds):
        raise ValueError("開場引用需要本聊天室的「分身有術企劃書」與「InnoServe 競賽須知」相關頁面，請確認已上傳可讀取文字的完整 PDF。")
    context = "\n\n".join(
        f"[{i}] {s['title']}\n{s['content']}" for i, s in enumerate(sources, 1)
    )
    required = [
        {refs["project_intro"], refs["project_audience"]},
        {refs["project_intro"], refs["project_features"], refs["project_citations"]},
        {refs["competition_scoring"]},
    ]
    system = (
        f"你是{user_name}的數位分身，為「分身有術如何在 InnoServe 資訊應用組得名」介紹背景。"
        "用第一人稱、繁體中文，約 300～400 字，只輸出三段，段落間空一行，不加標題。"
        "第一段介紹作品、問題與目標使用者；第二段介紹個人分身、多角色討論、RAG 引用與圖譜；"
        "第三段介紹資訊應用組決賽六項評分名稱與權重，再邀請其他分身提出看法。"
        "每段必須在相關敘述句尾標註實際文件的 [編號]，只用提供的編號，不把引用獨立放一段。"
        "具體敘述以文件為準，評分名稱與數字使用競賽須知原文；背景摘要與文件不同時，以文件為準。"
        "作品目標不說成已驗證成效，未來規劃不說成已實現功能。不替其他分身預先下結論。"
        f"{_DISCUSSION_RESPONSE_STYLE}"
    )
    user = (
        f"【主題】{topic}\n【背景】{discussion_brief}\n\n【可引用的實際文件頁面】\n{context}\n\n"
        + "\n".join(f"第 {i} 段應引用：" + "".join(f"[{ref}]" for ref in sorted(group))
                    for i, group in enumerate(required, 1))
    )
    for attempt in range(2):
        text = _normalize_cite_markers(_llm(client, model, system, user, temperature=0.5))
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
        valid = len(paragraphs) == 3
        for paragraph, expected in zip(paragraphs, required):
            found = {int(n) for n in re.findall(r"\[(\d+)\]", paragraph)}
            valid = valid and expected <= found and all(1 <= n <= len(sources) for n in found)
        if valid:
            return text, [], sources
        if attempt == 0:
            user += "\n上次輸出未符合三段與來源編號要求。請重新撰寫，每段附上對應的有效編號。"

    # 模型漏標兩次時改用附來源的文件摘錄；不假造引用或送出沒有引用的開場。
    sections = []
    for title, group in zip(("專題背景與使用對象", "系統功能與操作", "資訊應用組決賽評分"), required):
        excerpts = [f"{sources[ref - 1]['content']}[{ref}]" for ref in sorted(group)]
        sections.append(title + "（文件摘錄）：\n" + "\n".join(excerpts))
    sections.append("接下來討論分身有術如何在 InnoServe 資訊應用組得名，請各分身提出自己的觀點與建議。")
    return "\n\n".join(sections), [], sources


def _reply_user_twin(
    client: Any,
    model: str,
    *,
    user_name: str,
    topic: str,
    twin_context: str,
    discussion_brief: str,
    history_text: str,
    phase: str,
    user_id: int | None = None,
    session_id: int | None = None,
    top_k: int = 8,
) -> tuple[str, list[int], list[dict[str, Any]]]:
    if phase == "opening" and _is_innoserve_award_topic(topic) and user_id and session_id:
        return _reply_innoserve_opening(
            client, model, user_name=user_name, topic=topic, discussion_brief=discussion_brief,
            user_id=user_id, session_id=session_id,
        )
    phase_hint = "開場" if phase == "opening" else "回應討論"
    user_rag_context = ""
    chunk_ids: list[int] = []
    sources: list[dict[str, Any]] = []
    if user_id:
        rag_q = f"{topic} {discussion_brief} {history_text[-500:]}"
        user_rag_context, chunk_ids, sources = _user_rag_context(user_id, rag_q, top_k)
        if session_id:
            from web.knowledge import user_rag

            sess_ctx, sess_ids, sess_src = user_rag.search_session_context(
                user_id, session_id, rag_q, top_k=min(6, top_k)
            )
            if sess_ctx.strip():
                # 與下方來源陣列順序一致：聊天室資料先編號，私人資料接續編號。
                private_ctx = (
                    format_context(sources, start_index=len(sess_src) + 1)
                    if sources
                    else user_rag_context
                )
                user_rag_context = (
                    f"{sess_ctx}\n\n{private_ctx}"
                    if private_ctx.strip()
                    else sess_ctx
                )
                chunk_ids = sess_ids + chunk_ids
                sources = sess_src + sources

    cite_rule = (
        "【引用規則】若依據【你的私人資料】發言，句尾標 [1][2]…；"
        "資料未涵蓋時用一般文字說明資料不足，不要加不能點擊的引用標籤。"
    )
    twin_cross = (
        "必須具體回應【目前討論】中名人的觀點（點名），並結合【你的私人資料】補充事實；"
        "不可忽略他人已說的話。"
        if phase != "opening"
        else "開場可簡述立場；若討論中已有名人發言，須點名回應。"
    )
    length_hint = (
        "繁體中文，開場約 300～400 字，分成兩到三個短段落；依開場任務介紹作品與比賽後提出問題。"
        if phase == "opening" and _is_innoserve_award_topic(topic)
        else "繁體中文，開場約 120～180 字；辯論回應約 140～200 字，需回應名人觀點。"
    )
    system = (
        f"你是{user_name}的數位分身，主題「{topic}」，這是{phase_hint}。"
        f"{twin_context}\n"
        f"{twin_cross}\n"
        f"{cite_rule if user_id else ''}\n"
        f"{_DISCUSSION_RESPONSE_STYLE}\n"
        f"{length_hint}"
    )
    user = (
        f"【你的私人資料（使用者曾與分身分享）】\n{user_rag_context}\n\n"
        f"【議題】\n{discussion_brief}\n\n"
        f"【目前討論】\n{history_text or '（無）'}\n\n"
        f"請以{user_name}的分身身份發言，並與契合度高的名人同樣積極參與。"
    )
    text = _llm(client, model, system, user, temperature=0.78)
    return text, chunk_ids, sources


def _user_rag_context(user_id: int, query: str, top_k: int) -> tuple[str, list[int], list[dict[str, Any]]]:
    from web.knowledge import user_rag

    return user_rag.search_user_context(user_id, query, top_k=top_k)


def _cross_talk_rules(phase: str, prior_in_round: list[dict[str, str]]) -> str:
    """要求名人依先前發言與參考資料交叉討論。"""
    if prior_in_round:
        names = "、".join(dict.fromkeys(r["name"] for r in prior_in_round if r.get("name")))
        return (
            f"必須直接回應【本輪已發言】的 {names}：指出你同意、反駁或補充的具體觀點，"
            "並用【你的參考資料】補充可查證的事實（句尾 [編號]）；延伸做法用建議語氣，不加無依據的引用。"
            "不可自說自話、不可只打招呼。"
        )
    if phase == "opening":
        return (
            "開場須表明立場；若【先前討論】已有他人發言，必須點名回應。"
            "事實須來自【你的參考資料】並標 [編號]；延伸做法用建議語氣，不加無依據的引用。"
        )
    return (
        "必須承接【先前討論】已出現的觀點，點名至少一位與會者再延伸；"
        "事實來自【你的參考資料】並標 [編號]；延伸做法用建議語氣，不加無依據的引用。"
    )


def _length_hint_for_fit(
    topic_fit_score: int | None,
    phase: str,
    *,
    richer_personal_context: bool = False,
) -> str:
    score = 50 if topic_fit_score is None else int(topic_fit_score)
    if richer_personal_context:
        if phase == "opening":
            if score >= 78:
                return "約 200～260 字，引用並解釋 2～3 項個人資料中的具體知識或觀點"
            if score >= 52:
                return "約 160～220 字，運用至少 2 項個人資料中的具體知識或觀點"
            return "約 120～160 字；若個人資料有相關內容，挑出最相關的知識或觀點"
        if score >= 78:
            return "約 220～300 字，結合 2～3 項個人資料中的具體內容深入回應"
        if score >= 52:
            return "約 170～230 字，運用個人資料補充或比較他人觀點"
        return "約 130～170 字；若有相關資料則引用，延伸看法用建議語氣，不編造來源或事實"
    if phase == "opening":
        if score >= 78:
            return "約 160～240 字，務必深入表態"
        if score >= 52:
            return "約 110～170 字"
        return "約 60～95 字，簡短開場即可"
    if score >= 78:
        return "約 180～280 字，深入延伸、反駁與舉例"
    if score >= 52:
        return "約 120～190 字"
    return "約 65～100 字，簡短回應即可"


def _reply_celeb(
    client: Any,
    model: str,
    *,
    name_zh: str,
    topic: str,
    discussion_brief: str,
    history_text: str,
    context: str,
    phase: str,
    prior_in_round: list[dict[str, str]],
    topic_fit_score: int | None = None,
    direct_address: bool = False,
    independent_opening: bool = False,
    include_demo_suggestion: bool = False,
) -> str:
    others = ""
    if prior_in_round:
        others = "\n【本輪已發言】\n" + "\n".join(
            f"{r['name']}：{r['content']}" for r in prior_in_round
        )
    if direct_address:
        phase_hint = "回應使用者對你的提問"
    elif independent_opening:
        phase_hint = "獨立初步觀點"
    else:
        phase_hint = "開場" if phase == "opening" else "交叉回應"
    is_innoserve_demo = _is_innoserve_award_topic(topic)
    length_hint = _length_hint_for_fit(
        topic_fit_score,
        phase,
        richer_personal_context=is_innoserve_demo,
    )
    score = 50 if topic_fit_score is None else int(topic_fit_score)
    engagement = _fit_engagement_hint(topic_fit_score, phase)
    if is_innoserve_demo and score < 78:
        engagement = (
            "【契合度：中】請從自己的資料挑出至少兩項有關的知識或原則，再連結討論題目。"
            if score >= 52
            else "【契合度：低】簡短引用一項最相關的個人知識，並說明它能如何有限度地參考。"
        )
    temp = 0.72 if phase == "opening" else 0.78
    if score >= 78:
        temp = min(0.85, temp + 0.06)
    cross_talk = (
        "【初步觀點】這是交叉討論前的獨立表態。只根據討論主題與自己的參考資料，"
        "若個人資料有足夠依據，優先挑出 2～3 個具體概念、原則或例證來說明自己的立場；"
        "只挑資料支持的內容，不硬湊例證或數量；"
        "說明這些資料與當前主題的關聯，選擇自己最有依據的角度提出初步看法；"
        "不要提及、回應或猜測其他人的發言。"
        if independent_opening
        else _cross_talk_rules(phase, prior_in_round)
    )
    no_repeat = (
        "【避免重複】勿再說「大家好我是…」等開場寒暄；"
        "辯論輪次須回應他人新觀點或提出新例證，禁止複述自己上一則的相同段落。"
    )
    innoserve_round_hint = (
        "【本場發言重點】把主要篇幅放在自己資料中的概念、例證與理由，說明它們如何支持對主題的看法。"
        "後續回覆應補充新的資料或比較不同主張，不重複上一輪的案例。"
        if is_innoserve_demo
        else ""
    )
    if is_innoserve_demo:
        innoserve_round_hint += (
            "【本輪指定建議】本輪由你提出一次完整系統 Demo 操作建議。先引用個人資料中的相關原則並解釋與主題的關係，"
            "再以自己的建議語氣，用一小段串起輸入主題、選擇分身、查看引用、討論、心智圖與結論。"
            "操作建議屬於你對此題目的延伸，不把它冒充成來源原文；只根據已提供的系統功能提出步驟。\n"
            if include_demo_suggestion
            else "Demo 操作建議已安排由一位名人在指定輪次提出，本輪聚焦個人資料與主題觀點，"
            "不主動追加或重複展示腳本；使用者明確追問展示方式時才針對問題回答。\n"
        )
    reference_guidance = (
        "【引用來源】本輪所有 [編號] 都只對應【分身個人資料｜主要依據】。"
        "若個人資料有相關內容，多找幾項知識、原則、例證或研究內容並引用該分身資料的 [編號]；"
        "【房主提供的情境背景｜沒有引用編號】只用來理解問題，提到其中事實時說明是房主提供的背景。"
        "不可把個人資料的編號貼在附件內容或其他人的說法後面。"
        "先說明個人資料實際支持的知識並引用，再自然說明與主題的關聯或延伸建議，不套用固定轉折句；"
        "資料未涵蓋該應用時，不可讓引用看起來支持未經證實的應用或成效。"
        "不硬湊引用；個人資料中的例證需忠於來源；延伸建議不冒充已完成的測試或成果。"
    )
    system = (
        f"你是{name_zh}的數位分身，主題「{topic}」，這是{phase_hint}。"
        f"{engagement}\n"
        f"{innoserve_round_hint}"
        f"{cross_talk}\n"
        f"{no_repeat}\n"
        f"{_CITE_RULE}\n"
        f"{reference_guidance}"
        f"{_DISCUSSION_RESPONSE_STYLE}\n"
        f"繁體中文，{length_hint}。"
    )
    response_instruction = (
        f"請以{name_zh}身份，根據主題與自己的參考資料獨立提出初步立場，不要回應任何與會者；"
        "有參考資料支持的內容才在句尾標註可點擊的 [編號]；直接說明觀點與建議，不附加制式資料缺漏聲明。"
        if independent_opening
        else f"請以{name_zh}身份發言：先呼應他人一句，再提出你的論點；有資料支持才在句尾標註可點擊的 [編號]，直接說明觀點與建議，不附加制式資料缺漏聲明。"
    )
    user = (
        f"【本輪可用資料】\n{context}\n\n"
        f"【先前討論】\n{history_text or '（無）'}\n"
        f"{others}\n\n"
        f"【議題】\n{discussion_brief}\n\n"
        f"【主題契合度】{score}/100\n\n"
        f"{response_instruction}"
    )
    return _llm(client, model, system, user, temperature=temp)


def _generate_conclusion(
    client: Any,
    model: str,
    *,
    topic: str,
    discussion_brief: str,
    transcript: str,
    participant_names: list[str],
) -> str:
    guests = "、".join(participant_names)
    is_innoserve_demo = _is_innoserve_award_topic(topic)
    innoserve_conclusion_hint = (
        "整理已發表的建議時，可標明它們對應的資訊應用組評分項目；只歸納對話已談及的關聯，"
        "不要為了補齊六項標準而新增意見，也不要把評分權重當成作品已取得的分數。"
        "Demo 操作建議只能歸納名人在紀錄中已說出的內容，並標明提出者；"
        "若名人未提出，就不要補寫展示流程，也不要把主持人的新想法歸給名人。"
        if is_innoserve_demo
        else ""
    )
    length_hint = "約 260～340 字" if is_innoserve_demo else "約 180～260 字"
    system = (
        "你是圓桌主持人，根據討論紀錄產出結論。"
        f"{_DISCUSSION_RESPONSE_STYLE}\n"
        "只以『共識』『分歧』『建議』三個小標分段，使用繁體中文。"
        "不要產生『待釐清問題』段落，也不要將該段改名為其他小標或額外附在結尾。"
        "共識只列出多位參與者明確支持的內容，不將沒有人反對當成一致同意。"
        "分歧說明誰的看法不同以及差異；若沒有明確分歧，寫『目前未出現明確分歧』，不可硬造爭論。"
        "建議只整理參與者已提出的做法，標明提出者。"
        "只依據討論紀錄，不從議題說明新增建議、事實或步驟。"
        f"{length_hint}。不需標註引用。{innoserve_conclusion_hint}"
    )
    user = (
        f"【主題】{topic}\n【議題】{discussion_brief}\n【與會】{guests}\n\n"
        f"【紀錄】\n{transcript}\n\n請產出討論結論。"
    )
    return _llm(client, model, system, user, temperature=0.5)


def _prior_since_last_user(
    messages: list[dict[str, Any]],
    user_name: str,
) -> list[dict[str, str]]:
    """使用者上一則插話之後的發言（用於插話後的單輪討論）。"""
    acc: list[dict[str, str]] = []
    for m in reversed(messages):
        if m.get("role") == "user":
            break
        if m.get("role") == "user_twin":
            acc.insert(0, {"name": f"{user_name}（分身）", "content": m["content"]})
        elif m.get("person_name_zh"):
            acc.insert(0, {"name": m["person_name_zh"], "content": m["content"]})
    return acc


def _prior_in_same_phase(
    messages: list[dict[str, Any]],
    phase: str,
    user_name: str,
) -> list[dict[str, str]]:
    """本 phase 內、本則結論前已發言者（用於開場/辯論輪序提示）。"""
    acc: list[dict[str, str]] = []
    for m in reversed(messages):
        if m.get("role") == "conclusion":
            break
        meta_phase = m.get("phase")
        if meta_phase and meta_phase != phase:
            continue
        if m.get("role") == "user":
            break
        if m.get("role") == "user_twin":
            acc.insert(0, {"name": f"{user_name}（分身）", "content": m["content"]})
        elif m.get("person_name_zh"):
            acc.insert(0, {"name": m["person_name_zh"], "content": m["content"]})
    return acc


def run_next_turn(
    *,
    session_id: int,
    members: list[dict[str, Any]],
    topic: str,
    user_name: str,
    twin_context: str,
    client: Any,
    model: str,
    top_k: int = 8,
    discussion_brief: str | None = None,
    include_user_twin: bool = True,
    user_avatar_url: str = "",
    user_id: int | None = None,
) -> dict[str, Any] | None:
    """執行下一則發言；若已全部完成則回傳 None。"""
    history = chat_store.list_messages(session_id)
    spec = get_next_turn(history, members, include_user_twin=include_user_twin)
    if not spec:
        return None

    brief = _discussion_brief(topic, discussion_brief or "")
    user_note = _latest_user_note(history, members, user_name)
    if user_note:
        brief = f"{brief}\n\n【使用者剛剛插話】{user_note}"

    history_text = _format_transcript(history, user_name, exclude_roles={"conclusion"})
    twin_label = f"{user_name}（分身）"
    celeb_names = [m["name_zh"] for m in members]

    if spec.kind == "user_twin":
        twin_brief = brief
        if spec.phase == "opening" and _is_innoserve_award_topic(topic):
            twin_brief += (
                "\n\n【InnoServe 開場任務】用第一人稱介紹我們以「分身有術——數位分身討論系統」"
                "參加 InnoServe 資訊應用組，不能只介紹比賽而略過作品。"
                "先依【房主提供的專題背景】說明作品想解決的思考盲點與討論難收斂問題、"
                "主要使用者，以及個人分身、多角色討論、RAG 可點擊引用、心智圖與討論路徑的核心功能；"
                "自然說明這些功能如何幫助理解觀點與判斷依據，不必列出所有技術工具或操作步驟。"
                "接著依【房主提供的資訊應用組（IP）評分標準】簡明介紹六項名稱與各自權重。"
                "最後提出「分身有術如何在 InnoServe 資訊應用組得名」，邀請其他分身從自己的專業與資料"
                "提出作品改善與展示建議。作品與評分背景可直接介紹，不編造引用編號；"
                "未來規劃不說成已完成的功能。這一則只交代背景與問題，不預先代替其他分身下結論，"
                "也不預先給出完整 Demo 操作建議，讓後續分身提出。"
            )
        raw, chunk_ids, sources = _reply_user_twin(
            client,
            model,
            user_name=user_name,
            topic=topic,
            twin_context=twin_context,
            discussion_brief=twin_brief,
            history_text=history_text,
            phase=spec.phase,
            user_id=user_id,
            session_id=session_id,
            top_k=top_k,
        )
        display, segments = parse_cited_reply(raw, sources)
        msg = chat_store.add_message(
            session_id,
            "user_twin",
            display,
            chunk_ids=chunk_ids,
            sources=sources,
            content_segments=segments,
            phase=spec.phase,
        )
        out = {
            **msg,
            "person_slug": None,
            "person_name_zh": twin_label,
            "avatar_url": user_avatar_url,
            "phase": spec.phase,
            "sources": sources,
            "content_segments": segments,
        }
        return out

    if spec.kind == "conclusion":
        participants = celeb_names + ([twin_label] if include_user_twin else [])
        text = _generate_conclusion(
            client,
            model,
            topic=topic,
            discussion_brief=brief,
            transcript=history_text,
            participant_names=participants,
        )
        msg = chat_store.add_message(
            session_id,
            "conclusion",
            text,
            chunk_ids=[],
            sources=[],
            phase="conclusion",
        )
        chat_store.update_session_summary(session_id, text[:2000])
        return {
            **msg,
            "person_slug": None,
            "person_name_zh": "討論結論",
            "phase": "conclusion",
            "sources": [],
            "content_segments": [],
        }

    member = spec.member
    if not member:
        return None

    slug = member["person_slug"]
    name_zh = member["name_zh"]
    is_innoserve_demo = _is_innoserve_award_topic(topic)
    rag_q = (
        f"{topic} {_INNOSERVE_PERSONAL_RAG_HINT}"
        if is_innoserve_demo
        else f"{topic} {brief}"
    )
    if spec.phase == "debate":
        rag_q += " " + history_text[-500:]

    fit_top_k = _rag_top_k_for_fit(
        member.get("topic_fit_score"),
        top_k,
        richer_personal_context=is_innoserve_demo,
    )
    context, chunk_ids, sources = _rag_context(slug, rag_q, fit_top_k)
    context, chunk_ids, sources = _append_session_context(
        context,
        chunk_ids,
        sources,
        user_id=user_id,
        session_id=session_id,
        query=(
            f"{topic} InnoServe 資訊應用組比賽規則與作品背景"
            if is_innoserve_demo
            else rag_q
        ),
        top_k=fit_top_k,
        persona_first=True,
    )
    independent_opening = (
        spec.phase == "opening" and _is_innoserve_award_topic(topic)
    )
    prior = (
        []
        if independent_opening
        else _prior_in_same_phase(history, spec.phase, user_name)
    )

    raw = _reply_celeb(
        client,
        model,
        name_zh=name_zh,
        topic=topic,
        discussion_brief=brief,
        history_text="" if independent_opening else history_text,
        context=context,
        phase=spec.phase,
        prior_in_round=prior,
        topic_fit_score=member.get("topic_fit_score"),
        independent_opening=independent_opening,
        include_demo_suggestion=_is_demo_suggestion_turn(
            topic, history, members, include_user_twin=include_user_twin,
        ),
    )
    display, segments = parse_cited_reply(raw, sources)
    packed = _pack_sources(sources, segments)
    if isinstance(packed, dict):
        packed["phase"] = spec.phase

    msg = chat_store.add_message(
        session_id,
        slug,
        display,
        person_slug=slug,
        chunk_ids=chunk_ids,
        sources=packed,
        phase=spec.phase,
        content_segments=segments,
    )
    return {
        **msg,
        "person_slug": slug,
        "person_name_zh": name_zh,
        "avatar_url": member.get("avatar_url") or "",
        "phase": spec.phase,
        "sources": sources,
        "content_segments": segments,
        "content_raw": raw,
    }


def _interjection_brief(
    topic: str,
    discussion_brief: str | None,
    history: list[dict[str, Any]],
    members: list[dict[str, Any]],
    user_name: str,
) -> str:
    brief = _discussion_brief(topic, discussion_brief or "")
    user_note = _latest_user_note(history, members, user_name)
    if user_note:
        brief = f"{brief}\n\n【使用者剛剛插話】{user_note}"
    return brief


def run_direct_reply(
    *,
    session_id: int,
    members: list[dict[str, Any]],
    topic: str,
    user_name: str,
    twin_context: str,
    client: Any,
    model: str,
    target: str,
    top_k: int = 8,
    discussion_brief: str | None = None,
    include_user_twin: bool = True,
    user_avatar_url: str = "",
    user_id: int | None = None,
) -> dict[str, Any] | None:
    """插話後只讓單一對象回應一次（名人 slug 或 user_twin）。"""
    target = (target or "").strip()
    if target == "all":
        return None
    if target == "user_twin" and not include_user_twin:
        return None

    history = chat_store.list_messages(session_id)
    brief = _interjection_brief(topic, discussion_brief, history, members, user_name)
    history_text = _format_transcript(history, user_name, exclude_roles={"conclusion"})
    phase = "debate"
    prior = _prior_since_last_user(history, user_name)
    twin_label = f"{user_name}（分身）"
    last_reply_to = ""
    for m in reversed(history):
        if m.get("role") == "user":
            last_reply_to = (m.get("reply_to") or "all").strip() or "all"
            break

    if target == "user_twin":
        raw, chunk_ids, sources = _reply_user_twin(
            client,
            model,
            user_name=user_name,
            topic=topic,
            twin_context=twin_context,
            discussion_brief=brief,
            history_text=history_text,
            phase=phase,
            user_id=user_id,
            session_id=session_id,
            top_k=top_k,
        )
        display, segments = parse_cited_reply(raw, sources)
        msg = chat_store.add_message(
            session_id,
            "user_twin",
            display,
            chunk_ids=chunk_ids,
            sources=sources,
            content_segments=segments,
            phase=phase,
        )
        return {
            **msg,
            "person_slug": None,
            "person_name_zh": twin_label,
            "avatar_url": user_avatar_url,
            "phase": phase,
            "sources": sources,
            "content_segments": segments,
        }

    member = next(
        (m for m in members if (m.get("person_slug") or "") == target),
        None,
    )
    if not member:
        return None

    slug = member["person_slug"]
    name_zh = member["name_zh"]
    direct = last_reply_to == slug
    is_innoserve_demo = _is_innoserve_award_topic(topic)
    rag_q = (
        f"{topic} {_INNOSERVE_PERSONAL_RAG_HINT} {history_text[-500:]}"
        if is_innoserve_demo
        else f"{topic} {brief} {history_text[-500:]}"
    )
    fit_top_k = _rag_top_k_for_fit(
        member.get("topic_fit_score"),
        top_k,
        richer_personal_context=is_innoserve_demo,
    )
    context, chunk_ids, sources = _rag_context(slug, rag_q, fit_top_k)
    context, chunk_ids, sources = _append_session_context(
        context,
        chunk_ids,
        sources,
        user_id=user_id,
        session_id=session_id,
        query=(
            f"{topic} InnoServe 資訊應用組比賽規則與作品背景"
            if is_innoserve_demo
            else rag_q
        ),
        top_k=fit_top_k,
        persona_first=True,
    )
    raw = _reply_celeb(
        client,
        model,
        name_zh=name_zh,
        topic=topic,
        discussion_brief=brief,
        history_text=history_text,
        context=context,
        phase=phase,
        prior_in_round=prior,
        topic_fit_score=member.get("topic_fit_score"),
        direct_address=direct,
    )
    display, segments = parse_cited_reply(raw, sources)
    packed = _pack_sources(sources, segments)
    if isinstance(packed, dict):
        packed["phase"] = phase
        if direct:
            packed["direct_reply"] = True
            packed["reply_to"] = slug
    msg = chat_store.add_message(
        session_id,
        slug,
        display,
        person_slug=slug,
        chunk_ids=chunk_ids,
        sources=packed,
        phase=phase,
        content_segments=segments,
    )
    return {
        **msg,
        "person_slug": slug,
        "person_name_zh": name_zh,
        "avatar_url": member.get("avatar_url") or "",
        "phase": phase,
        "sources": sources,
        "content_segments": segments,
    }


def run_interjection_round(
    *,
    session_id: int,
    members: list[dict[str, Any]],
    topic: str,
    user_name: str,
    twin_context: str,
    client: Any,
    model: str,
    top_k: int = 8,
    discussion_brief: str | None = None,
    include_user_twin: bool = True,
    user_avatar_url: str = "",
    user_id: int | None = None,
) -> dict[str, Any]:
    """插話給所有人：隨機名人順序，一位接一位回應（非同時）。"""
    ordered = [m for m in members if (m.get("person_slug") or m.get("slug") or "").strip()]
    random.shuffle(ordered)
    speaking_order: list[dict[str, Any]] = []
    replies: list[dict[str, Any]] = []

    for m in ordered:
        slug = m.get("person_slug") or ""
        if not slug:
            continue
        speaking_order.append(
            {
                "person_slug": slug,
                "name_zh": m.get("name_zh") or slug,
                "avatar_url": m.get("avatar_url") or "",
                "kind": "celeb",
                "topic_fit_score": m.get("topic_fit_score"),
            }
        )
        msg = run_direct_reply(
            session_id=session_id,
            members=members,
            topic=topic,
            user_name=user_name,
            twin_context=twin_context,
            client=client,
            model=model,
            target=slug,
            top_k=top_k,
            discussion_brief=discussion_brief,
            include_user_twin=include_user_twin,
            user_avatar_url=user_avatar_url,
            user_id=user_id,
        )
        if msg:
            msg["interjection_index"] = len(replies) + 1
            replies.append(msg)

    if include_user_twin:
        twin_label = f"{user_name}（分身）"
        speaking_order.append(
            {
                "person_slug": "user_twin",
                "name_zh": twin_label,
                "avatar_url": user_avatar_url,
                "kind": "user_twin",
                "topic_fit_score": None,
            }
        )
        twin_msg = run_direct_reply(
            session_id=session_id,
            members=members,
            topic=topic,
            user_name=user_name,
            twin_context=twin_context,
            client=client,
            model=model,
            target="user_twin",
            top_k=top_k,
            discussion_brief=discussion_brief,
            include_user_twin=include_user_twin,
            user_avatar_url=user_avatar_url,
            user_id=user_id,
        )
        if twin_msg:
            twin_msg["interjection_index"] = len(replies) + 1
            replies.append(twin_msg)

    total = len(replies)
    for msg in replies:
        msg["interjection_total"] = total

    return {"speaking_order": speaking_order, "replies": replies}


def run_roundtable(**kwargs: Any) -> list[dict[str, Any]]:
    """相容舊 API：改為迴圈呼叫 run_next_turn。"""
    out: list[dict[str, Any]] = []
    session_id = kwargs["session_id"]
    members = kwargs["members"]
    while True:
        msg = run_next_turn(**kwargs)
        if not msg:
            break
        out.append(msg)
    return out
