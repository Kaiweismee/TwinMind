"""從名人討論訊息產生心智圖與意見差距曲線資料。"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

INSIGHTS_LLM_EVERY_N = max(1, int(os.getenv("INSIGHTS_LLM_EVERY_N", "1")))

_NON_CELEB_ROLES = frozenset(
    {"user", "user_twin", "conclusion", "system", "moderator"}
)
_log = logging.getLogger(__name__)


def _mind_map_analysis_status(error: Any) -> str:
    if isinstance(error, dict):
        param = error.get("param")
        code = error.get("code")
        if param:
            return f"AI 請求被拒絕（{param}）"
        if code:
            return f"AI 請求失敗（{code}）"
        return f"AI 請求失敗（{error.get('type') or '未知錯誤'}）"
    if error == "invalid_json":
        return "AI 回覆格式錯誤"
    if error == "AuthenticationError":
        return "OpenAI API 金鑰驗證失敗"
    if error == "RateLimitError":
        return "OpenAI API 額度或頻率受限"
    if error == "APIConnectionError":
        return "無法連線 OpenAI API"
    if error == "BadRequestError":
        return "AI 請求格式或模型設定錯誤"
    if error == "APITimeoutError":
        return "OpenAI API 回應逾時"
    return "AI 摘要服務發生錯誤"


def _message_person_slug(m: dict[str, Any]) -> str:
    """盡量推回名人 slug；舊訊息缺 slug 時退而用姓名 key。"""
    slug = str(m.get("person_slug") or "").strip()
    if slug:
        return slug
    role = str(m.get("role") or "").strip()
    if role and role not in _NON_CELEB_ROLES and role not in {"assistant"}:
        return role
    name = str(m.get("person_name_zh") or "").strip()
    if name:
        return f"name::{name}"
    return ""


def _is_celeb_message(m: dict[str, Any]) -> bool:
    """名人發言：role 為 slug，或 assistant 且已關聯 person。"""
    role = (m.get("role") or "").strip()
    if role in _NON_CELEB_ROLES:
        return False
    if m.get("person_slug"):
        return True
    if role == "assistant" and m.get("person_name_zh"):
        return True
    return role not in _NON_CELEB_ROLES and bool(m.get("person_name_zh"))


def _discussion_lines(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    lines: list[dict[str, str]] = []
    for i, m in enumerate(messages):
        content = (m.get("content") or "").strip()
        if not content:
            continue
        if m.get("role") == "user":
            name = m.get("guest_name") or "使用者"
        elif m.get("role") == "user_twin":
            name = "你的分身"
        elif m.get("role") == "conclusion":
            name = "總結"
        elif _is_celeb_message(m):
            name = m.get("person_name_zh") or m.get("person_slug") or "名人"
        else:
            continue
        phase = m.get("phase") or "discussion"
        lines.append(
            {
                "index": str(i),
                "speaker": name,
                "person_slug": _message_person_slug(m),
                "phase": phase,
                "content": content[:800],
            }
        )
    return lines


def _member_lookup(members: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for m in members:
        slug = m.get("person_slug") or ""
        if slug:
            out[slug] = m
    return out


def _enrich_node_speakers(node: dict[str, Any], lookup: dict[str, dict[str, Any]]) -> None:
    slug = node.get("person_slug") or ""
    if slug and lookup.get(slug):
        m = lookup[slug]
        node.setdefault("speaker", m.get("name_zh") or slug)
        node.setdefault("avatar_url", m.get("avatar_url") or "")
    for child in node.get("children") or []:
        if isinstance(child, dict):
            _enrich_node_speakers(child, lookup)


_LOW_VALUE_OPENING_RE = re.compile(
    r"^(?:"
    r"哈[囉啰]|你好|您好|嗨|Hello|Hi\b|"
    r"大家(?:好|晚上好|午安)|各位(?:好|觀眾|朋友)|"
    r"很高興|幸會|歡迎|感謝(?:大家|各位)|謝謝(?:大家|各位)|"
    r"先(?:跟|和)大家|今天(?:很|非常)?高興|"
    r"我是[^，。！？]{0,16}[，。！？]?|"
    r"讓我(?:先|來)?(?:自我)?介紹|"
    r"接下來(?:想|要)?(?:和|跟)大家"
    r")",
    re.IGNORECASE,
)

_SUBSTANTIVE_MARKERS_RE = re.compile(
    r"認為|覺得|應該|必須|需要|可能|無法|不能|"
    r"風險|機會|問題|影響|挑戰|建議|擔心|支持|反對|"
    r"因為|所以|然而|但是|如果|雖然|"
    r"就業|技術|AI|人工智慧|監管|倫理|創新|效率|"
    r"\d+[%％]?|[%％]"
)


_AGREE_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"(?:我(?:同意|認同|贊同|支持)|我也同意|我完全同意)[^，。；:：]{0,28}[，。；:：]\s*|"
    r"(?:我想(?:補充|回應|延伸)|我補充一下|我回應一下)[^，。；:：]{0,28}[，。；:：]\s*|"
    r"(?:正如|如同|回應|針對)[^，。；:：]{0,28}(?:提到|指出|所說|說過)[^，。；:：]{0,12}[，。；:：]\s*|"
    r"(?:謝謝|感謝)[^，。；:：]{0,20}[，。；:：]\s*"
    r")+",
    re.IGNORECASE,
)

_DISCOURSE_PREFIX_RE = re.compile(
    r"^\s*(?:(?:首先|其次|再者|此外|另外|同時|因此|所以|最後|總之|換句話說|總結來說)"
    r"[，、；:：\s]*)+",
    re.IGNORECASE,
)

_INTERACTION_TONE_RE = re.compile(
    r"(?:我同意|我認同|我贊同|我支持|謝謝|感謝|回應|補充|延伸|呼應|你提到|他提到|她提到)",
    re.IGNORECASE,
)

_CLAIM_REASON_MARKERS_RE = re.compile(
    r"(?:因為|因此|所以|意味著|顯示|代表|導致|風險|機會|影響|建議|應該|需要|不能|必須)"
)

_TOPIC_MIN_SCORE = float(os.getenv("INSIGHTS_TOPIC_MIN_SCORE", "8"))
_MAX_THEME_PER_SPEAKER = max(1, int(os.getenv("INSIGHTS_MAX_THEME_PER_SPEAKER", "2")))
_GENERIC_VAGUE_RE = re.compile(
    r"^(?:隨著AI技術的進步|AI的影響力|這種能力|這種現象|我們應該更關注|未來將會)",
    re.IGNORECASE,
)


def _self_view_text(text: str) -> str:
    """
    將「同意某人」這類承接語去頭，保留名人的自身觀點內容。
    目標是讓心智圖與重點摘要更像「這位名人的立場」而非互相附和句。
    """
    s = (text or "").strip()
    if not s:
        return ""
    s = _AGREE_PREFIX_RE.sub("", s).strip()
    s = _DISCOURSE_PREFIX_RE.sub("", s).strip()
    return s


def _is_claim_reason_sentence(text: str) -> bool:
    """
    僅保留「主張 + 理由/影響」的句子，避免純互動語氣。
    """
    s = (text or "").strip()
    if len(s) < 10:
        return False
    if _INTERACTION_TONE_RE.search(s[:28]):
        return False
    if _is_low_value_sentence(s):
        return False
    markers = len(_CLAIM_REASON_MARKERS_RE.findall(s))
    substantive = len(_SUBSTANTIVE_MARKERS_RE.findall(s))
    return markers >= 1 or substantive >= 2


def _topic_terms(topic: str) -> list[str]:
    terms: list[str] = []
    for t in re.findall(r"[\u4e00-\u9fff]{2,}", topic or ""):
        if t not in terms:
            terms.append(t)
        # 長詞拆成 2~4 字關鍵片段，避免整句比對過嚴
        if len(t) >= 4:
            max_n = min(4, len(t))
            for n in range(2, max_n + 1):
                for i in range(0, len(t) - n + 1):
                    seg = t[i : i + n]
                    if seg not in terms:
                        terms.append(seg)
    for t in re.findall(r"[a-zA-Z]{3,}", topic or ""):
        tl = t.lower()
        if tl not in terms:
            terms.append(tl)
    return terms


def _topic_relevance_score(sentence: str, topic: str) -> float:
    s = (sentence or "").strip()
    if not s:
        return -100.0
    if _GENERIC_VAGUE_RE.search(s):
        return -20.0
    terms = _topic_terms(topic)
    if not terms:
        return 0.0
    hits = sum(1 for t in terms if t and t in s)
    if hits == 0:
        return -30.0
    return hits * 10.0


def _strip_citations(text: str) -> str:
    return re.sub(r"\[\d+\]|\[推論\]", "", text or "").strip()


def _split_sentences(content: str) -> list[str]:
    text = re.sub(r"\s+", " ", _strip_citations(content))
    if not text:
        return []
    parts = re.split(r"(?<=[。！？!?])\s*|\n+", text)
    sentences: list[str] = []
    for part in parts:
        part = part.strip()
        if len(part) < 4:
            continue
        if len(part) >= 28 and _is_low_value_sentence(part):
            for clause in re.split(r"[，,；;]", part):
                clause = clause.strip()
                if len(clause) >= 8:
                    sentences.append(clause)
        else:
            sentences.append(part)
    if not sentences and text:
        sentences = [text]
    return sentences


def _is_low_value_sentence(sentence: str) -> bool:
    s = re.sub(r"\s+", "", (sentence or "").strip())
    if len(s) < 6:
        return True
    if _LOW_VALUE_OPENING_RE.search(s):
        if len(s) <= 28 and not _SUBSTANTIVE_MARKERS_RE.search(s):
            return True
    if len(s) <= 14 and not _SUBSTANTIVE_MARKERS_RE.search(s):
        return True
    greet_only = re.fullmatch(
        r"(?:哈[囉啰]|你好|您好|嗨)+[！!。]?|大家(?:好|晚上好)[！!。]?|"
        r"(?:很高興|感謝|謝謝).{0,18}[！!。]?",
        s,
    )
    return bool(greet_only)


def _sentence_substance_score(sentence: str, topic: str = "") -> float:
    s = (sentence or "").strip()
    if not s:
        return -100.0
    score = min(len(s), 80) * 0.35
    score += len(_SUBSTANTIVE_MARKERS_RE.findall(s)) * 8.0
    if topic:
        for kw in re.findall(r"[\u4e00-\u9fff]{2,}", topic):
            if len(kw) >= 2 and kw in s:
                score += 4.0
    if _is_low_value_sentence(s):
        score -= 60.0
    if re.match(
        r"^(?:哈[囉啰]|你好|您好|嗨|大家|各位|很高興|感謝|謝謝|今天)",
        s,
    ):
        score -= 28.0
    if re.search(r"[：:]\s*$", s) and len(s) < 20:
        score -= 15.0
    return score


def _extract_substantive_snippet(text: str, max_len: int, topic: str = "") -> str:
    """全文滑窗：當整段都是開場白時，仍盡量擷取有論點的片段。"""
    clean = re.sub(r"\s+", " ", _strip_citations(text))
    if not clean:
        return ""
    win = min(max_len + 24, len(clean))
    if len(clean) <= max_len:
        return clean if not _is_low_value_sentence(clean) else ""
    best = ""
    best_score = -1.0
    step = max(8, win // 3)
    for i in range(0, max(1, len(clean) - win + 1), step):
        chunk = clean[i : i + win]
        sc = _sentence_substance_score(chunk, topic)
        if sc > best_score:
            best_score = sc
            best = chunk
    if best_score < 5:
        return ""
    if len(best) > max_len:
        return best[: max_len - 1].rstrip() + "…"
    return best


def _message_highlight(content: str, max_len: int = 48, topic: str = "") -> str:
    """從整段發言擷取一句實質重點（略過寒暄、問候）。"""
    text = re.sub(r"\s+", " ", _strip_citations(content))
    text = _self_view_text(text)
    if not text:
        return ""

    sentences = _split_sentences(text)
    best = ""
    best_score = -999.0
    for s in sentences:
        if not _is_claim_reason_sentence(s):
            continue
        score = _sentence_substance_score(s, topic)
        if score > best_score:
            best_score = score
            best = s

    if not best or _is_low_value_sentence(best):
        fallback = _extract_substantive_snippet(text, max_len, topic)
        if fallback and _is_claim_reason_sentence(fallback):
            best = fallback
        elif len(sentences) > 1:
            for s in sorted(sentences, key=len, reverse=True):
                if _is_claim_reason_sentence(s):
                    best = s
                    break
        elif sentences:
            tail = sentences[-1]
            if _is_claim_reason_sentence(tail):
                best = tail

    best = re.sub(r"^[^：:]+[：:]\s*", "", (best or "").strip())
    if not best or _is_low_value_sentence(best):
        return ""

    if len(best) > max_len:
        return best[: max_len - 1].rstrip() + "…"
    return best


def _compact_point(text: str, *, topic: str = "", max_len: int = 26) -> str:
    """將文本壓成短重點，避免整段敘述塞進心智圖節點。"""
    raw = _self_view_text((text or "").strip())
    if not raw:
        return ""
    clauses = [
        c.strip()
        for c in re.split(r"[，,；;。!?！？]\s*", raw)
        if c.strip()
    ]
    if not clauses:
        clauses = [raw]

    best = ""
    best_score = -999.0
    for c in clauses:
        if len(c) < 6:
            continue
        score = _sentence_substance_score(c, topic)
        score -= max(0, len(c) - max_len) * 0.7
        if score > best_score:
            best_score = score
            best = c

    if not best:
        best = raw
    if len(best) > max_len:
        return best[: max_len - 1].rstrip() + "…"
    return best


def _theme_keywords(label: str, topic: str = "") -> list[str]:
    for lbl, kws in _theme_buckets_for_topic(topic):
        if lbl == label:
            return kws
    return []


def _build_speech_highlights(
    lines: list[dict[str, str]],
    *,
    topic: str = "",
    max_items: int = 5,
    max_len: int = 28,
) -> list[str]:
    """從名人發言整理面板「發言重點」chips。"""
    by_slug: dict[str, tuple[float, str]] = {}
    for line in lines:
        slug = line.get("person_slug") or ""
        if not slug:
            continue
        hl_raw = _message_highlight(line["content"], 96, topic)
        hl = _compact_point(hl_raw, topic=topic, max_len=max_len)
        if not hl:
            continue
        if _topic_relevance_score(hl, topic) < 0:
            continue
        score = _sentence_substance_score(hl, topic)
        label = f"{line['speaker']}：{hl}"
        prev = by_slug.get(slug)
        if prev is None or score > prev[0]:
            by_slug[slug] = (score, label)

    ranked = sorted(by_slug.values(), key=lambda x: x[0], reverse=True)
    return [label for _, label in ranked[:max_items]]


_MIND_MAP_THEME_BUCKETS: list[tuple[str, list[str]]] = [
    (
        "就業與勞動市場",
        [
            "就業", "工作", "失業", "勞動", "職位", "裁員", "人力", "僱用", "取代",
            "求職", "職場", "競爭力", "薪資", "裁撤", "招募",
        ],
    ),
    (
        "技術能力與限制",
        [
            "技術", "能力", "限制", "模型", "AGI", "演算法", "資料", "訓練", "智能",
            "算力", "GPU", "深度學習", "準確", "幻覺",
        ],
    ),
    (
        "風險與治理",
        [
            "風險", "安全", "監管", "倫理", "威脅", "危險", "隱私", "偏見",
            "治理", "法規", "責任", "偏誤", "造假",
        ],
    ),
    (
        "機會與創新",
        [
            "機會", "效率", "創新", "生產力", "助益", "合作", "賦能", "突破",
            "轉型", "優勢", "提升", "自動化", "個性化",
        ],
    ),
]

_REPLACE_TOPIC_THEME_BUCKETS: list[tuple[str, list[str]]] = [
    ("取代風險", ["取代", "被取代", "失業", "淘汰", "消失", "裁員"]),
    ("不可替代能力", ["創造力", "情感", "同理", "倫理判斷", "批判思維", "人性"]),
    ("人機協作與增強", ["協作", "合作", "輔助", "增強", "共創", "效率提升"]),
    ("治理與教育轉型", ["治理", "監管", "法規", "教育", "課程", "培訓", "轉型"]),
]

_INNOSERVE_DEMO_THEME_BUCKETS: list[tuple[str, list[str]]] = [
    (
        "檢索引用與可信度",
        ["檢索", "引用", "來源", "參考資料", "可信", "查證", "可追", "資料不足"],
    ),
    (
        "公平呈現與視覺化",
        ["公平", "平衡", "立場", "觀點", "視覺化", "心智圖", "偏見", "角色", "發言"],
    ),
    (
        "決策流程與完整系統演練",
        ["流程", "系統演練", "完整系統", "情境", "展示", "demo", "決策", "操作", "實際"],
    ),
    (
        "使用者需求與產品價值",
        ["使用者", "需求", "痛點", "產品", "價值", "客戶", "效益"],
    ),
    (
        "成效驗證與展示溝通",
        ["驗證", "測試", "指標", "成效", "海報", "簡報", "評審", "溝通"],
    ),
]


def _is_innoserve_award_topic(topic: str) -> bool:
    normalized = re.sub(r"[\W_]+", "", (topic or "").casefold())
    has_award_intent = any(
        word in normalized for word in ("得名", "得獎", "獲獎", "獲名次", "拿名次")
    )
    return any(name in normalized for name in ("innoserve", "分身有術")) and has_award_intent


def _theme_buckets_for_topic(topic: str) -> list[tuple[str, list[str]]]:
    t = topic or ""
    if _is_innoserve_award_topic(t):
        return _INNOSERVE_DEMO_THEME_BUCKETS
    if any(k in t for k in ("取代", "人類", "替代", "失業")):
        return _REPLACE_TOPIC_THEME_BUCKETS
    return _MIND_MAP_THEME_BUCKETS


def _branch_order_for_topic(topic: str) -> list[str]:
    return [label for label, _ in _theme_buckets_for_topic(topic)] + [
        "討論結論",
        "討論重點",
    ]


_MIND_MAP_BRANCH_ORDER = [label for label, _ in _MIND_MAP_THEME_BUCKETS] + [
    "討論結論",
    "討論重點",
]


def _canonical_mind_map_branch_label(label: str, index: int = 0, topic: str = "") -> str:
    """還原 LLM 或截斷標籤為完整子議題名稱。"""
    branch_order = _branch_order_for_topic(topic)
    buckets = _theme_buckets_for_topic(topic)
    raw = re.sub(
        r"^[\s★⚙💡♥⚠➤◆●\-\·…\.]+",
        "",
        str(label or "").strip(),
    )
    if not raw or raw in ("...", "…"):
        if 0 <= index < len(branch_order):
            return branch_order[index]
        return "討論重點"
    for canonical in branch_order:
        if canonical in raw or raw in canonical:
            return canonical
    best_label = raw
    best_score = 0
    for canonical, keywords in buckets:
        score = _theme_score_for_text(raw, keywords)
        if score > best_score:
            best_score = score
            best_label = canonical
    if best_score > 0:
        return best_label
    if len(raw) <= 6 and 0 <= index < len(branch_order):
        return branch_order[index]
    return raw

_PHASE_MIND_LABELS = frozenset(
    {
        "開場",
        "開場觀點",
        "辯論",
        "辯論交鋒",
        "總結",
        "討論",
        "結論",
        "opening",
        "debate",
        "conclusion",
        "discussion",
    }
)


def _theme_score_for_text(text: str, keywords: list[str]) -> int:
    return sum(1 for kw in keywords if kw in text)


def _pick_mind_map_theme(text: str, topic: str) -> str:
    best_label = "討論重點"
    best_score = 0
    combined = f"{topic} {text}"
    buckets = _theme_buckets_for_topic(topic)
    for label, keywords in buckets:
        score = _theme_score_for_text(combined, keywords)
        if score > best_score:
            best_score = score
            best_label = label
    if best_score == 0:
        for label, keywords in buckets:
            if any(kw in topic for kw in keywords):
                return label
    return best_label


def _mind_map_leaf(
    speaker: str,
    person_slug: str,
    content: str,
    topic: str = "",
) -> dict[str, Any]:
    is_innoserve_demo = _is_innoserve_award_topic(topic)
    quote_full = _message_highlight(content, 150 if is_innoserve_demo else 110, topic)
    display_len = 45
    quote_short = _compact_point(quote_full or content, topic=topic, max_len=display_len)
    if not quote_short and quote_full:
        quote_short = _compact_point(quote_full, topic=topic, max_len=display_len)
    if not quote_full:
        quote_full = quote_short
    return {
        "label": quote_short or quote_full,
        "quote": quote_short or quote_full,
        "quote_full": quote_full or quote_short,
        "speaker": speaker,
        "person_slug": person_slug,
    }


_SKIP_MIND_MAP_SLUGS = frozenset({"user_twin", "user", "conclusion", ""})
_SKIP_MIND_MAP_SPEAKERS = frozenset({"你的分身", "總結", "使用者"})


def _discussion_celebrities(
    members: list[dict[str, Any]],
    lines: list[dict[str, str]],
) -> list[tuple[str, str]]:
    celebs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for m in members:
        slug = str(m.get("person_slug") or "").strip()
        if not slug or slug in _SKIP_MIND_MAP_SLUGS:
            continue
        name = str(m.get("name_zh") or m.get("person_slug") or slug).strip()
        if slug not in seen:
            seen.add(slug)
            celebs.append((slug, name))
    if celebs:
        return celebs
    for line in lines:
        slug = str(line.get("person_slug") or "").strip()
        if not slug or slug in _SKIP_MIND_MAP_SLUGS:
            continue
        speaker = str(line.get("speaker") or "").strip()
        if speaker in _SKIP_MIND_MAP_SPEAKERS:
            continue
        if slug not in seen:
            seen.add(slug)
            celebs.append((slug, speaker or slug))
    return celebs


def _score_sentence_for_theme(sentence: str, theme_label: str, topic: str) -> float:
    """句子與子議題的相關度；無關鍵字命中則回傳負分（避免硬塞同一段）。"""
    keywords = _theme_keywords(theme_label, topic)
    kw_hits = _theme_score_for_text(sentence, keywords)
    if kw_hits <= 0:
        return -1.0
    topic_sc = _topic_relevance_score(sentence, topic)
    if topic_sc < 0:
        return -1.0
    return kw_hits * 10.0 + topic_sc + _sentence_substance_score(sentence, topic) * 0.22


def _iter_celeb_sentences(lines: list[dict[str, str]], slug: str) -> list[str]:
    sentences: list[str] = []
    for line in lines:
        if line.get("person_slug") != slug:
            continue
        if (line.get("phase") or "") == "conclusion":
            continue
        if (line.get("speaker") or "").strip() in _SKIP_MIND_MAP_SPEAKERS:
            continue
        for sent in _split_sentences(line.get("content") or ""):
            s = _self_view_text(sent).strip()
            if len(s) < 8 or not _is_claim_reason_sentence(s):
                continue
            sentences.append(s)
    return sentences


def _assign_mind_map_leaves(
    topic: str,
    lines: list[dict[str, str]],
    celebs: list[tuple[str, str]],
    *,
    min_score: float | None = None,
    max_theme_per_speaker: int | None = None,
) -> dict[str, list[tuple[str, str, str]]]:
    """
    將每位名人的「句子」分配到最相關的子議題；每句全域只用一次。
    回傳 theme_label -> [(slug, name, sentence), ...]
    """
    themes = [label for label, _ in _theme_buckets_for_topic(topic)]
    result: dict[str, list[tuple[str, str, str]]] = {t: [] for t in themes}
    used: set[str] = set()
    score_floor = _TOPIC_MIN_SCORE if min_score is None else float(min_score)
    speaker_cap = (
        _MAX_THEME_PER_SPEAKER
        if max_theme_per_speaker is None
        else max(1, int(max_theme_per_speaker))
    )

    ranked: list[tuple[float, str, str, str, str]] = []
    for slug, name in celebs:
        for sent in _iter_celeb_sentences(lines, slug):
            for theme in themes:
                sc = _score_sentence_for_theme(sent, theme, topic)
                if sc >= 0:
                    ranked.append((sc, theme, slug, name, sent))

    ranked.sort(key=lambda x: (-x[0], x[2], x[1]))
    theme_slugs: dict[str, set[str]] = {t: set() for t in themes}
    speaker_theme_count: dict[str, int] = {}

    for _sc, theme, slug, name, sent in ranked:
        if _sc < score_floor:
            continue
        key = f"{slug}|{sent[:120]}"
        if key in used or slug in theme_slugs[theme]:
            continue
        if speaker_theme_count.get(slug, 0) >= speaker_cap:
            continue
        used.add(key)
        theme_slugs[theme].add(slug)
        speaker_theme_count[slug] = speaker_theme_count.get(slug, 0) + 1
        result[theme].append((slug, name, sent))

    # 至少讓每位名人有機會出現在一個最貼切節點（避免「某人完全不見」）
    represented = {
        slug
        for rows in result.values()
        for slug, _name, _sent in rows
    }
    if len(represented) < len(celebs):
        by_slug_rows: dict[str, list[tuple[float, str, str, str]]] = {}
        for sc, theme, slug, name, sent in ranked:
            by_slug_rows.setdefault(slug, []).append((sc, theme, name, sent))
        for slug, name in celebs:
            if slug in represented:
                continue
            rows = by_slug_rows.get(slug) or []
            if not rows:
                continue
            rows.sort(key=lambda x: x[0], reverse=True)
            for sc, theme, _name, sent in rows:
                if sc < max(2.0, score_floor - 4.0):
                    continue
                key = f"{slug}|{sent[:120]}"
                if key in used:
                    continue
                used.add(key)
                result[theme].append((slug, name, sent))
                represented.add(slug)
                break

    return result


def _build_mind_map_children(
    topic: str,
    lines: list[dict[str, str]],
    members: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """中心主題 → 有實質內容的子議題 → 各名人相關觀點（跨分支不重複）。"""
    celebs = _discussion_celebrities(members, lines)
    if not celebs:
        return []

    themes = [label for label, _ in _theme_buckets_for_topic(topic)]
    is_innoserve_demo = _is_innoserve_award_topic(topic)
    assigned = _assign_mind_map_leaves(
        topic,
        lines,
        celebs,
        max_theme_per_speaker=len(themes) if is_innoserve_demo else None,
    )
    children: list[dict[str, Any]] = []
    for theme_label in themes:
        leaves: list[dict[str, Any]] = []
        for slug, name, sentence in assigned.get(theme_label, []):
            leaf = _mind_map_leaf(name, slug, sentence, topic)
            leaf["theme_label"] = theme_label
            leaves.append(leaf)
        if leaves:
            children.append({"label": theme_label, "children": leaves})

    # 只放寬門檻尋找有實際內容的新議題，不補固定數量的分類。
    if children:
        relaxed = _assign_mind_map_leaves(
            topic,
            lines,
            celebs,
            min_score=max(2.0, _TOPIC_MIN_SCORE - 4.0),
            max_theme_per_speaker=max(_MAX_THEME_PER_SPEAKER, 3),
        )
        existing_labels = {c.get("label") for c in children}
        for theme_label in themes:
            if theme_label in existing_labels:
                continue
            leaves: list[dict[str, Any]] = []
            for slug, name, sentence in (relaxed.get(theme_label) or [])[:2]:
                leaf = _mind_map_leaf(name, slug, sentence, topic)
                leaf["theme_label"] = theme_label
                leaves.append(leaf)
            if leaves:
                children.append({"label": theme_label, "children": leaves})
    if not children:
        return []
    return children


def _mind_map_uses_phase_branches(children: list[Any]) -> bool:
    if not children:
        return False
    labels = {str(c.get("label") or "").strip() for c in children if isinstance(c, dict)}
    return bool(labels & _PHASE_MIND_LABELS)


def _mind_map_uses_speaker_branches(
    children: list[Any],
    members: list[dict[str, Any]],
) -> bool:
    if len(children) < 2:
        return False
    names: set[str] = set()
    for m in members:
        if m.get("name_zh"):
            names.add(str(m["name_zh"]))
        if m.get("person_slug"):
            names.add(str(m["person_slug"]))
    hit = 0
    for child in children:
        if not isinstance(child, dict):
            continue
        if str(child.get("label") or "") in names:
            hit += 1
    return hit >= max(2, len(children) // 2)


def _score_from_message_text(text: str) -> float | None:
    """依單則發言估算立場分數（0–100），供軌跡上下起伏。"""
    snippet = (text or "")[:400]
    pos = len(re.findall(r"支持|樂|乐观|機會|創新|贊成|應該|可以|同意", snippet))
    neg = len(re.findall(r"風險|擔心|反對|問題|危險|不應|困難|限制|懷疑", snippet))
    if pos + neg == 0:
        return None
    return round(20 + (pos / (pos + neg)) * 60, 1)


_PHASE_LABELS = {
    "opening": "開場",
    "debate": "辯論",
    "conclusion": "總結",
    "discussion": "討論",
}


def _build_trajectory(
    messages: list[dict[str, Any]],
    members: list[dict[str, Any]],
    chart_points: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """依發言順序建立時間軸，供前端橫向滑動檢視。"""
    lookup = _member_lookup(members)
    phase_scores: dict[str, dict[str, float]] = {}
    for pt in chart_points:
        phase = pt.get("phase") or "discussion"
        phase_scores[phase] = pt.get("scores") or {}

    trajectory: list[dict[str, Any]] = []
    step = 0
    for m in messages:
        if not _is_celeb_message(m):
            continue
        slug = _message_person_slug(m)
        member = lookup.get(slug)
        if not member:
            fallback_name = m.get("person_name_zh") or slug.replace("name::", "")
            if not fallback_name:
                continue
            member = {
                "name_zh": fallback_name,
                "avatar_url": m.get("avatar_url") or "",
            }
        content = (m.get("content") or "").strip()
        if not content:
            continue
        step += 1
        phase = m.get("phase") or "discussion"
        scores = phase_scores.get(phase) or {}
        phase_score = scores.get(slug)
        msg_score = _score_from_message_text(content)
        if msg_score is not None:
            score = msg_score
        elif phase_score is not None:
            score = float(phase_score)
        else:
            score = 50.0
        trajectory.append(
            {
                "step": step,
                "phase": phase,
                "phase_label": _PHASE_LABELS.get(phase, phase),
                "label": member.get("name_zh") or slug,
                "person_slug": slug,
                "name_zh": member.get("name_zh") or slug,
                "avatar_url": member.get("avatar_url") or "",
                "score": float(score),
                "quote": content[:400],
                "summary": _message_highlight(content, 96),
                "highlight": _message_highlight(content, 48),
            }
        )
    return trajectory


def _cluster_overlap_threshold() -> float:
    return 8.0


def _enrich_chart_opinions(
    messages: list[dict[str, Any]],
    members: list[dict[str, Any]],
    chart: dict[str, Any],
) -> None:
    """為每個階段附上名人原話，供前端點擊查看。"""
    lookup = _member_lookup(members)
    threshold = _cluster_overlap_threshold()
    for pt in chart.get("points") or []:
        phase = pt.get("phase") or "discussion"
        opinions: dict[str, Any] = {}
        for m in messages:
            if not _is_celeb_message(m):
                continue
            if (m.get("phase") or "discussion") != phase:
                continue
            slug = _message_person_slug(m)
            member = lookup.get(slug)
            if not member:
                fallback_name = m.get("person_name_zh") or slug.replace("name::", "")
                if not fallback_name:
                    continue
                member = {
                    "name_zh": fallback_name,
                    "avatar_url": m.get("avatar_url") or "",
                }
            content = (m.get("content") or "").strip()
            if not content:
                continue
            opinions[slug] = {
                "speaker": member.get("name_zh") or slug,
                "person_slug": slug,
                "avatar_url": member.get("avatar_url") or "",
                "quote": content[:240],
                "summary": _message_highlight(content, 80),
            }
        pt["opinions"] = opinions
        scores = pt.get("scores") or {}
        if len(scores) >= 2:
            vals = [float(v) for v in scores.values()]
            pt["max_gap"] = round(max(vals) - min(vals), 1)
            pt["aligned"] = pt["max_gap"] <= threshold
        elif scores:
            pt.setdefault("max_gap", 0.0)
            pt["aligned"] = True
        else:
            pt["aligned"] = len(opinions) <= 1


def _finalize_insights(
    result: dict[str, Any],
    messages: list[dict[str, Any]],
    members: list[dict[str, Any]],
) -> dict[str, Any]:
    chart = result.get("stance_chart") or {}
    _enrich_chart_opinions(messages, members, chart)
    chart["timeline"] = _build_trajectory(messages, members, chart.get("points") or [])
    chart["trajectory"] = chart["timeline"]
    result["stance_chart"] = chart
    return result


def _fallback_insights(
    topic: str,
    members: list[dict[str, Any]],
    lines: list[dict[str, str]],
) -> dict[str, Any]:
    """無 LLM 時的簡易規則版分析。"""
    slug_to_name = {
        (m.get("person_slug") or ""): (m.get("name_zh") or m.get("person_slug") or "")
        for m in members
    }

    children = _build_mind_map_children(topic or "討論主題", lines, members)

    phases_seen: list[str] = []
    for line in lines:
        p = line.get("phase") or "discussion"
        if p not in phases_seen:
            phases_seen.append(p)

    phase_labels = {
        "opening": "開場",
        "debate": "辯論",
        "conclusion": "結論",
        "discussion": "討論",
    }
    steps: list[dict[str, Any]] = []
    scores_by_slug: dict[str, list[float]] = {
        m.get("person_slug") or "": [] for m in members
    }

    step_idx = 0
    for phase in phases_seen or ["discussion"]:
        step_idx += 1
        scores: dict[str, float] = {}
        phase_lines = [l for l in lines if l.get("phase") == phase and l.get("person_slug")]
        for m in members:
            slug = m.get("person_slug") or ""
            name = m.get("name_zh") or slug
            person_lines = [l for l in phase_lines if l.get("person_slug") == slug]
            if not person_lines:
                continue
            text = " ".join(l["content"] for l in person_lines)
            pos = len(re.findall(r"支持|樂觀|機會|創新|贊成|應該|可以", text))
            neg = len(re.findall(r"風險|擔心|反對|問題|危險|不應|困難|限制", text))
            score = 50.0
            if pos + neg > 0:
                score = round(20 + (pos / (pos + neg)) * 60, 1)
            scores[slug] = score
            scores_by_slug.setdefault(slug, []).append(score)
        if scores:
            vals = list(scores.values())
            max_gap = round(max(vals) - min(vals), 1) if len(vals) > 1 else 0.0
            steps.append(
                {
                    "step": step_idx,
                    "phase": phase,
                    "label": phase_labels.get(phase, phase),
                    "scores": scores,
                    "max_gap": max_gap,
                }
            )

    if not steps:
        steps = [
            {
                "step": 1,
                "phase": "opening",
                "label": "開場",
                "scores": {},
                "max_gap": 0,
            }
        ]

    highlights = _build_speech_highlights(lines, topic=topic or "")
    if not highlights and len(lines) >= 2:
        highlights.append(f"共 {len(lines)} 則發言，等待實質論點摘錄")
    for slug, vals in scores_by_slug.items():
        if len(vals) >= 2 and slug_to_name.get(slug) and len(highlights) < 5:
            spread = max(vals) - min(vals)
            if spread >= 15:
                highlights.append(f"{slug_to_name[slug]} 立場變化 {spread:.0f} 分")

    fake_messages = [
        {
            "role": line["person_slug"],
            "person_slug": line["person_slug"],
            "person_name_zh": line["speaker"],
            "content": line["content"],
            "phase": line.get("phase") or "discussion",
        }
        for line in lines
        if line.get("person_slug")
    ]
    result = {
        "mind_map": {
            "title": topic or "討論主題",
            "children": children,
        },
        "stance_chart": {
            "topic": topic or "討論立場",
            "axis_label_low": "保守 / 謹慎",
            "axis_label_high": "積極 / 樂觀",
            "series": [
                {
                    "person_slug": m.get("person_slug") or "",
                    "name_zh": m.get("name_zh") or m.get("person_slug") or "",
                    "avatar_url": m.get("avatar_url") or "",
                }
                for m in members
            ],
            "points": steps,
            "overlap_threshold": _cluster_overlap_threshold(),
        },
        "highlights": highlights or ["持續討論後會更新重點摘要"],
        "source": "heuristic",
    }
    return _finalize_insights(result, fake_messages, members)


def _parse_json_block(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def _normalize_insights(
    raw: dict[str, Any],
    topic: str,
    members: list[dict[str, Any]],
    *,
    lines: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    mind = raw.get("mind_map") or {}
    if not mind.get("title"):
        mind["title"] = topic or "討論主題"
    if not mind.get("children"):
        mind["children"] = []

    chart = raw.get("stance_chart") or {}
    if not chart.get("topic"):
        chart["topic"] = topic or "討論立場"
    chart.setdefault("axis_label_low", "保守 / 謹慎")
    chart.setdefault("axis_label_high", "積極 / 樂觀")
    lookup = _member_lookup(members)
    if not chart.get("series"):
        chart["series"] = [
            {
                "person_slug": m.get("person_slug") or "",
                "name_zh": m.get("name_zh") or m.get("person_slug") or "",
                "avatar_url": m.get("avatar_url") or "",
            }
            for m in members
        ]
    else:
        for s in chart["series"]:
            slug = s.get("person_slug") or ""
            if slug in lookup:
                s.setdefault("name_zh", lookup[slug].get("name_zh") or slug)
                s.setdefault("avatar_url", lookup[slug].get("avatar_url") or "")
    chart.setdefault("points", [])
    chart["overlap_threshold"] = _cluster_overlap_threshold()

    _enrich_node_speakers(mind, lookup)
    for child in mind.get("children") or []:
        if isinstance(child, dict):
            child["label"] = str(child.get("label") or "討論重點").strip()
            _enrich_node_speakers(child, lookup)

    return {
        "mind_map": mind,
        "stance_chart": chart,
        "highlights": raw.get("highlights") or [],
        "source": raw.get("source") or "llm",
    }


def generate_insights(
    *,
    topic: str,
    members: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    client: Any | None = None,
    model: str = "gpt-4o-mini",
) -> dict[str, Any]:
    lines = _discussion_lines(messages)
    if len(lines) < 2:
        base = _fallback_insights(topic, members, lines)
        base["highlights"] = ["至少需要 2 則發言才能產生圖譜"]
        base["ready"] = False
        return _finalize_insights(base, messages, members)

    if client is None:
        result = _fallback_insights(topic, members, lines)
        result["ready"] = True
        return _finalize_insights(result, messages, members)

    member_desc = "、".join(
        f"{m.get('name_zh')}({m.get('person_slug')})" for m in members
    )
    is_innoserve_demo = _is_innoserve_award_topic(topic)
    transcript_limit = 60 if is_innoserve_demo else 40
    transcript = "\n".join(
        f"[{l['phase']}] {l['speaker']}: {l['content']}"
        for l in lines[-transcript_limit:]
    )
    mind_map_quote_length = "30-50"

    innoserve_mind_map_rules = (
        "- 本場 InnoServe 心智圖以「檢索引用與可信度」、「公平呈現與視覺化」、"
        "「決策流程與完整系統演練」作為起始方向，不限制只能三個議題。"
        "若實際發言另談到使用者需求、產品價值、成效驗證、簡報或海報溝通等獨立主張，建立相應新議題；"
        "內容充足時可整理 4～8 個不同議題，沒有內容的分類先不要畫出來，不為湊數拆分近義議題。\n"
        "- 決策流程議題優先整理發言中的判斷方法與使用價值；只有實際對話提到完整系統演練時才收錄其操作建議，合併重複流程，不替每位名人補上 Demo 建議。\n"
        "- 優先整理名人在個人資料引用中提到的專業知識、原則、研究內容或具體例證；比賽規章與專題內容只在發言確實談到時才納入。\n"
        "- 發言若明確將建議連結到資訊應用組評分項目，摘要保留該關聯；只沿用紀錄中的項目與權重，不新增評分、不強制建立六個分類。\n"
        "- 每個分身的內容要統整成可展示的建議，勿照抄整段聊天室發言；同一名人可以出現在多個相關議題，"
        "每個議題下若有兩項不同的實質主張，可分成兩張觀點卡；相同或近義觀點合併，保留先前仍有效的觀點。\n"
        if _is_innoserve_award_topic(topic)
        else ""
    )

    system = (
        "你是討論分析助手。根據多人對話產出 JSON，供前端繪製心智圖與立場曲線。"
        "只輸出合法 JSON，不要 markdown。"
    )
    user = f"""討論主題：{topic}
參與名人：{member_desc}

對話紀錄：
{transcript}

請輸出 JSON：
{{
  "mind_map": {{
    "title": "與討論主題相同的一句話",
    "children": [
      {{
        "label": "依本場對話歸納出的實際議題名稱",
        "children": [
          {{
            "label": "該名人對此議題整理後的核心重點",
            "quote": "以 {mind_map_quote_length} 字白話說明核心觀點，再補充一個具體做法、理由或影響",
            "speaker": "中文名",
            "person_slug": "slug"
          }}
        ]
      }}
    ]
  }},
  "stance_chart": {{
    "topic": "主要爭點描述",
    "axis_label_low": "保守端標籤",
    "axis_label_high": "積極端標籤",
    "series": [{{"person_slug": "slug", "name_zh": "中文名"}}],
    "points": [
      {{
        "step": 1,
        "phase": "opening|debate|conclusion",
        "label": "階段名",
        "scores": {{"person_slug": 0-100 的立場分數}},
        "max_gap": 該步最大差距
      }}
    ]
  }},
  "highlights": ["3-5 個一眼看懂的重點"]
}}

規則：
- mind_map 結構：中心 title=討論主題 → 第二層=依對話內容自行歸納的議題 → 第三層=各名人在該議題下整理後的重點
- 議題數量由內容決定；輸出所有清楚且彼此不同的議題，通常 2-8 個，內容尚少時可少於 2 個；不可湊固定數量，不可加入沒有實際觀點的分類
{innoserve_mind_map_rules}- 議題名稱貼合本場討論，允許使用全新的分類；不要把近義議題拆開湊數
- 禁止用「開場／辯論／總結」或流程階段當第二層；禁止把名人姓名當第二層
- 每個葉節點含 speaker、person_slug、quote（或 label）；quote 約 {mind_map_quote_length} 字，最多 60 字，以一到兩個白話短句說明同一個核心觀點；label 與 quote 使用相同摘要
- quote 必須是摘要而非逐字摘錄：不要照抄原句、不要使用引號或第一人稱；忠於發言，不加入對話未提及的事實
- 用一般人一眼能懂的日常用語，優先說清楚「要做什麼」或「主要看法」；避免抽象名詞堆疊、術語與縮寫，需要時換成簡單說法
- 每張卡先說主要看法，再從發言中補充一個具體做法、理由、例子或影響，讓讀者知道為什麼或怎麼做；避免只剩空泛口號。原發言沒有細節時保持簡短，不為湊字數編造理由
- 不必同時塞入主張、例證、理由與影響，不列多項清單、不重複議題名稱。句子太長時重新改寫，不用省略號或截斷句子湊字數
- 保留會改變立場的否定、條件與不確定性，例如「可能」「先驗證再擴大」「尚未證實」；不可為縮短而把建議寫成事實或把未知寫成確定
- 只收錄確實談及該議題的名人；不可在多個議題重複相同重點
- quote／highlights 必須是實質論點（立場、理由、影響、建議），禁止「哈囉大家好」「很高興參與」等寒暄開場
- 不把 AI 身分、真人背書、得名機率或全面公平等制式聲明列為心智圖觀點或 highlights；保留對具體問題的驗證方法與有依據的限制
- 不摘錄「個人資料未證明能得名」「未提供本作品的成效測試、壓力測試或迭代紀錄」這類附帶聲明；若同段有具體測試做法或改進建議，只整理該做法。不得因此把未知效果改寫成已驗證的成果
- quote / highlights 不要以「我同意某某」「謝謝某某」開頭，請直接寫該名人的自身立場與理由
- quote 與 highlights 保留核心主張及一項有依據的補充說明，避免只有回應語氣或純社交用語
- 跨每位名人的相關發言整理不同主張，不要只取第一句或最長的一句；同一議題下每位名人最多兩個不同重點，每張卡只講一個重點
- stance_chart 至少 2 個 step，scores 的 key 必須用 person_slug
- 分數 0=最保守，100=最積極；若立場相近，分數應接近（前端會重疊頭像）
"""

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        text = (resp.choices[0].message.content or "").strip()
        parsed = _parse_json_block(text)
        if not parsed:
            _log.warning("Mind-map analysis returned invalid JSON")
            result = _fallback_insights(topic, members, lines)
            result["ready"] = True
            result["mind_map_analysis_error"] = "invalid_json"
            return _finalize_insights(result, messages, members)
        result = _normalize_insights(parsed, topic, members, lines=lines)
        result["ready"] = True
        result["source"] = "llm"
        return _finalize_insights(result, messages, members)
    except Exception as exc:
        error_type = type(exc).__name__
        error_param = getattr(exc, "param", None)
        error_code = getattr(exc, "code", None)
        _log.warning(
            "Mind-map analysis request failed: type=%s param=%s code=%s",
            error_type,
            error_param if isinstance(error_param, str) else "",
            error_code if isinstance(error_code, str) else "",
        )
        result = _fallback_insights(topic, members, lines)
        result["ready"] = True
        result["mind_map_analysis_error"] = {
            "type": error_type,
            "param": error_param if isinstance(error_param, str) else None,
            "code": error_code if isinstance(error_code, str) else None,
        }
        return _finalize_insights(result, messages, members)


_insights_cache: dict[tuple[int, int], dict[str, Any]] = {}
_insights_llm_at: dict[int, int] = {}


def _hydrate_llm_at_from_db(session_id: int) -> None:
    if session_id in _insights_llm_at:
        return
    try:
        from web.repositories.chat_store import load_session_insights

        row = load_session_insights(session_id)
        if row and row.get("llm_message_count"):
            _insights_llm_at[session_id] = int(row["llm_message_count"])
    except Exception:
        pass


def get_cached_insights(session_id: int, message_count: int) -> dict[str, Any] | None:
    key = (session_id, message_count)
    if key in _insights_cache:
        return _insights_cache[key]
    try:
        from web.repositories.chat_store import load_session_insights

        row = load_session_insights(session_id)
        if not row:
            return None
        stored_count = int(row.get("message_count") or 0)
        data = row.get("insights")
        if not isinstance(data, dict):
            return None
        _insights_cache[(session_id, stored_count)] = data
        llm_n = int(row.get("llm_message_count") or 0)
        if llm_n > 0:
            _insights_llm_at[session_id] = llm_n
        if stored_count == message_count:
            return data
    except Exception:
        return None
    return None


def get_stored_insights_snapshot(session_id: int) -> dict[str, Any] | None:
    """最近一次寫入 DB 的圖譜（訊息數可與現在不同）。"""
    try:
        from web.repositories.chat_store import load_session_insights

        row = load_session_insights(session_id)
        if not row or not isinstance(row.get("insights"), dict):
            return None
        return {
            "insights": row["insights"],
            "message_count": int(row.get("message_count") or 0),
            "llm_message_count": int(row.get("llm_message_count") or 0),
            "updated_at": row.get("updated_at"),
        }
    except Exception:
        return None


def set_cached_insights(session_id: int, message_count: int, data: dict[str, Any]) -> None:
    _insights_cache[(session_id, message_count)] = data
    if len(_insights_cache) > 64:
        oldest = next(iter(_insights_cache))
        _insights_cache.pop(oldest, None)
    llm_n = _insights_llm_at.get(session_id, 0)
    try:
        from web.repositories.chat_store import save_session_insights

        save_session_insights(
            session_id,
            message_count,
            data,
            llm_message_count=llm_n,
        )
    except Exception:
        pass


def should_use_llm_for_insights(session_id: int, message_count: int, *, force: bool) -> bool:
    if force:
        return True
    if message_count < 2:
        return False
    _hydrate_llm_at_from_db(session_id)
    last = _insights_llm_at.get(session_id, 0)
    if last <= 0:
        return True
    return (message_count - last) >= INSIGHTS_LLM_EVERY_N


def mark_llm_insights(session_id: int, message_count: int) -> None:
    _insights_llm_at[session_id] = message_count


def get_last_llm_insights(session_id: int) -> dict[str, Any] | None:
    _hydrate_llm_at_from_db(session_id)
    last_count = _insights_llm_at.get(session_id, 0)
    if last_count <= 0:
        return None
    cached = get_cached_insights(session_id, last_count)
    if cached:
        return cached
    snap = get_stored_insights_snapshot(session_id)
    if snap and snap["llm_message_count"] == last_count:
        return snap["insights"]
    return None


def build_session_insights(
    *,
    session_id: int,
    topic: str,
    members: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    message_count: int,
    client: Any | None = None,
    model: str = "gpt-4o-mini",
    force: bool = False,
    live_only: bool = False,
) -> dict[str, Any]:
    """
    邊討論邊更新：每則發言用輕量規則即時畫圖；每 N 則或強制刷新時才呼叫 OpenAI。
    live_only=True：平時使用上一版 AI 摘要；累積足夠新發言後再自動重做分類與摘要。
    """
    if live_only:
        lines = _discussion_lines(messages)
        mind_map_analysis_error = None
        if client and len(lines) >= 2 and should_use_llm_for_insights(
            session_id, message_count, force=force
        ):
            result = generate_insights(
                topic=topic,
                members=members,
                messages=messages,
                client=client,
                model=model,
            )
            if result.get("source") == "llm":
                mark_llm_insights(session_id, message_count)
                result["ready"] = True
                result["update_mode"] = "ai"
                result["update_label"] = "AI 已統整討論重點"
                result["mind_map_format_version"] = 2
                return _finalize_insights(result, messages, members)
            mark_llm_insights(session_id, message_count)
            mind_map_analysis_error = result.get("mind_map_analysis_error") or "analysis_failed"

        result = _fallback_insights(topic, members, lines)
        if mind_map_analysis_error:
            result["mind_map_analysis_error"] = mind_map_analysis_error
        if client:
            # 等候下一次 AI 統整時保留上版摘要，不把即時摘句誤當成心智圖重點。
            previous = get_last_llm_insights(session_id)
            previous_map = previous.get("mind_map") if isinstance(previous, dict) else None
            if previous and previous.get("mind_map_format_version", 0) >= 2:
                result["mind_map"] = previous_map or {"title": topic or "討論主題", "children": []}
                result["mind_map_format_version"] = 2
            else:
                result["mind_map"] = {"title": topic or "討論主題", "children": []}
        result["ready"] = len(lines) >= 1
        result["update_mode"] = "live"
        n = len(lines)
        result["update_label"] = (
            f"{_mind_map_analysis_status(mind_map_analysis_error)} · 點 ↻ 重試"
            if mind_map_analysis_error
            else f"等待 AI 統整 · 已含 {n} 則發言" if n else "等待討論開始"
        )
        speech_hl = _build_speech_highlights(lines, topic=topic or "")
        result["highlights"] = speech_hl or result.get("highlights") or []
        return _finalize_insights(result, messages, members)

    use_llm = bool(client) and should_use_llm_for_insights(
        session_id, message_count, force=force
    )

    if use_llm:
        result = generate_insights(
            topic=topic,
            members=members,
            messages=messages,
            client=client,
            model=model,
        )
        ai_summary_ready = result.get("source") == "llm"
        result["update_mode"] = "ai" if ai_summary_ready else "live"
        result["update_label"] = (
            "AI 已統整討論重點"
            if ai_summary_ready
            else f"{_mind_map_analysis_status(result['mind_map_analysis_error'])} · 點 ↻ 重試"
            if result.get("mind_map_analysis_error")
            else "等待 AI 重點整理"
        )
        result["mind_map_format_version"] = 2 if ai_summary_ready else 1
        mark_llm_insights(session_id, message_count)
        return result

    lines = _discussion_lines(messages)
    result = _fallback_insights(topic, members, lines)
    result["ready"] = len(lines) >= 2
    result["update_mode"] = "live"
    result["update_label"] = "即時更新"

    speech_hl = _build_speech_highlights(lines, topic=topic or "")
    if speech_hl:
        result["highlights"] = speech_hl
    return _finalize_insights(result, messages, members)
