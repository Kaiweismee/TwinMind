/* js/insights.js */
const INSIGHTS_LINE_COLORS = ["#6366f1", "#ec4899", "#0ea5e9", "#f59e0b", "#10b981", "#8b5cf6"];
// 預設使用 live 增量更新，避免心智圖每次都大幅重算。
// 手動按「刷新」時才會走 AI 深度分析（refresh=1）。
const INSIGHTS_PREFER_AI = false;
let insightsOpen = false;
let insightsFetchTimer = null;
let insightsInFlight = false;
let lastInsightsMsgCount = 0;
function toggleInsightsPanel(open) {
  const body = document.getElementById("chatBody");
  const panel = document.getElementById("insightsPanel");
  const rail = document.getElementById("insightsRail");
  const btn = document.getElementById("insightsPanelToggle");
  const topBtn = document.getElementById("btnInsightsTop");
  if (!body || !panel) return;
  insightsOpen = open ?? !insightsOpen;
  body.classList.toggle("insights-open", insightsOpen);
  rail?.classList.toggle("is-open", insightsOpen);
  panel.setAttribute("aria-hidden", insightsOpen ? "false" : "true");
  btn?.setAttribute("aria-expanded", insightsOpen ? "true" : "false");
  topBtn?.setAttribute("aria-expanded", insightsOpen ? "true" : "false");
  if (btn) {
    const label = insightsOpen ? "收合圖譜" : "展開圖譜";
    btn.title = label;
    btn.setAttribute("aria-label", label);
  }
  topBtn?.classList.toggle("active", insightsOpen);
  if (!insightsOpen) {
    mindMapHistoryModalOpen = false;
  } else {
    scheduleInsightsRefresh(false);
  }
}


function maybeAutoOpenInsights(messages, discussionDone = false) {
  const celebCount = (messages || []).filter(
    (m) => m.person_slug && !["user", "user_twin", "conclusion"].includes(m.role)
  ).length;
  if (discussionDone || celebCount >= 1) toggleInsightsPanel(true);
}

function syncInsightsTopButton() {
  document.getElementById("btnInsightsTop")?.classList.toggle("active", insightsOpen);
}

function clearInsightsPanel() {
  lastInsightsMsgCount = 0;
  mindMapHistoryModalOpen = false;
  if (currentSessionId) setMindMapPreviewIndex(currentSessionId, null);
  const highlights = document.getElementById("insightsHighlights");
  const mind = document.getElementById("mindMapHost");
  const chart = document.getElementById("stanceChartHost");
  const legend = document.getElementById("stanceGapLegend");
  if (highlights) highlights.innerHTML = "";
  if (mind) {
    const topic = currentSession ? sessionTopic(currentSession) : '討論主題';
    const initialMind = { title: topic, children: [] };
    if (currentSessionId) mindMapLatestBySession.set(currentSessionId, cloneJsonSafe(initialMind));
    renderMindMap(initialMind);
  }
  if (chart) chart.innerHTML = '<p class="insights-empty">尚無名人發言紀錄</p>';
  if (legend) legend.innerHTML = "";
}

function scheduleInsightsRefresh(force = false, immediate = false) {
  if (!currentSessionId) return;
  if (!insightsOpen && !force) return;
  if (insightsFetchTimer) clearTimeout(insightsFetchTimer);
  insightsFetchTimer = setTimeout(() => {
    fetchAndRenderInsights(force).catch(() => {});
  }, force || immediate ? 0 : 280);
}

function scheduleInsightsLiveUpdate(immediate = true) {
  if (!currentSessionId) return;
  if (!insightsOpen) toggleInsightsPanel(true);
  scheduleInsightsRefresh(INSIGHTS_PREFER_AI, immediate);
}

async function fetchAndRenderInsights(force = false) {
  if (!currentSessionId || insightsInFlight) return;
  insightsInFlight = true;
  document.getElementById("mindMapUpdateStatus")?.removeAttribute("hidden");
  const refreshBtn = document.getElementById("btnInsightsRefresh");
  refreshBtn?.classList.add("spinning");
  try {
    const useAi = force || INSIGHTS_PREFER_AI;
    const q = useAi ? "?refresh=1" : "?live=1";
    const data = await fetchJson(
      `/api/sessions/${currentSessionId}/insights${q}`,
      {},
      currentSessionId
    );
    const nextMessageCount = Number(data.message_count) || 0;
    const previousMind = currentSessionId ? mindMapLatestBySession.get(currentSessionId) || null : null;
    renderInsights(data.insights || {}, {
      // renderMindMap 會依 key 比對差異；每次允許動畫，只有新節點才會播放。
      animate: true,
      previousMind,
      messageCount: nextMessageCount,
    });
    lastInsightsMsgCount = nextMessageCount;
  } catch (err) {
    const mind = document.getElementById("mindMapHost");
    const scroll = mind?.querySelector(".mind-map-paper-scroll");
    if (scroll) {
      const error = document.createElement("p");
      error.className = "insights-empty";
      error.textContent = err.message || "無法載入圖譜";
      scroll.replaceChildren(error);
    } else if (mind) {
      const error = document.createElement("p");
      error.className = "insights-empty";
      error.textContent = err.message || "無法載入圖譜";
      mind.appendChild(error);
    }
  } finally {
    insightsInFlight = false;
    document.getElementById("mindMapUpdateStatus")?.setAttribute("hidden", "");
    refreshBtn?.classList.remove("spinning");
  }
}

function measureTextWidth(text, fontSize = 11, weight = 400) {
  const c = measureTextWidth._c || (measureTextWidth._c = document.createElement("canvas"));
  const ctx = c.getContext("2d");
  ctx.font = `${weight} ${fontSize}px -apple-system, BlinkMacSystemFont, "PingFang TC", sans-serif`;
  return ctx.measureText(text).width;
}

function renderInsights(insights, { animate = false, previousMind = null, messageCount = lastInsightsMsgCount } = {}) {
  const hint = document.querySelector(".insights-panel-hint");
  if (hint) {
    if (insights.stale) {
      hint.textContent = "已載入儲存的圖譜 · 有新發言可點 ↻ 更新";
      hint.classList.remove("insights-panel-hint--ai");
      hint.classList.add("insights-panel-hint--live");
    } else {
      const mode = insights.update_mode === "ai" ? "ai" : "live";
      hint.textContent =
        insights.update_label ||
        (mode === "ai"
          ? "AI 深度分析 · 已儲存"
          : "即時更新中 · 每 3 則發言自動 AI 深度分析");
      hint.classList.toggle("insights-panel-hint--ai", mode === "ai");
      hint.classList.toggle("insights-panel-hint--live", mode === "live");
    }
  }

  const highlights = document.getElementById("insightsHighlights");
  if (highlights) {
    highlights.innerHTML = "";
    for (const h of insights.highlights || []) {
      const chip = document.createElement("div");
      chip.className = "insights-highlight-chip";
      chip.textContent = h;
      highlights.appendChild(chip);
    }
  }
  if (currentSessionId && insights?.mind_map) {
    const hasAiSummary = Number(insights.mind_map_format_version) >= 2;
    const visibleMind = hasAiSummary
      ? cleanMindMap(insights.mind_map)
      : { title: insights.mind_map.title || sessionTopic(currentSession), children: [] };
    mindMapLatestBySession.set(currentSessionId, cloneJsonSafe(visibleMind));
    if (hasAiSummary && hasMindMapChildren(visibleMind)) {
      upsertMindMapHistory(currentSessionId, visibleMind, messageCount);
    }
    const history = getMindMapHistory(currentSessionId);
    const idx = getMindMapPreviewIndex(currentSessionId);
    if (idx != null && idx >= history.length - 1) {
      // 停在最後一格時，自動跟著最新版本走。
      setMindMapPreviewIndex(currentSessionId, null);
    }
  }
  try {
    const isPreviewingHistory = getMindMapPreviewIndex(currentSessionId) != null;
    const mindToRender = getActiveMindMapForSession(currentSessionId, cleanMindMap(insights.mind_map || {}));
    const emptyLabel = insights.ai_available === false
      ? '設定 OpenAI API 後即可統整名人觀點'
      : insights.mind_map_analysis_error
        ? 'AI 摘要暫時失敗，點 ↻ 重試'
      : messageCount < 2
        ? '討論開始後會逐步整理觀點'
        : 'AI 正在整理目前的討論';
    renderMindMap(mindToRender || {}, {
      animate: animate && !isPreviewingHistory,
      previousMind: isPreviewingHistory ? null : previousMind,
      emptyLabel,
    });
  } catch (err) {
    console.error("renderMindMap", err);
    const mind = document.getElementById("mindMapHost");
    if (mind) {
      mind.innerHTML = `<p class="insights-empty">心智圖渲染失敗：${escapeHtml(err.message || String(err))}</p>`;
    }
  }
  try {
    renderStanceChart(insights.stance_chart || {});
  } catch (err) {
    console.error("renderStanceChart", err);
    const chart = document.getElementById("stanceChartHost");
    if (chart) {
      chart.innerHTML = `<p class="insights-empty">曲線圖渲染失敗：${escapeHtml(err.message || String(err))}</p>`;
    }
  }
}

function insightsPersonMeta(slug, seriesItem) {
  const fromSeries = seriesItem || {};
  const m = (currentSession?.members || []).find((x) => x.person_slug === slug);
  return {
    slug,
    name: fromSeries.name_zh || m?.name_zh || slug || "名人",
    avatar: fromSeries.avatar_url || m?.avatar_url || personAvatarUrl(slug) || "",
  };
}

let insightsClipId = 0;

function insightSvgId(slug) {
  return String(slug || "x").replace(/[^a-zA-Z0-9_-]/g, "_");
}

function svgDefsAvatarClip(svg, slug, size) {
  const NS = "http://www.w3.org/2000/svg";
  const id = `insight-clip-${insightSvgId(slug)}-${insightsClipId++}`;
  let defs = svg.querySelector("defs");
  if (!defs) {
    defs = document.createElementNS(NS, "defs");
    svg.insertBefore(defs, svg.firstChild);
  }
  const clip = document.createElementNS(NS, "clipPath");
  clip.setAttribute("id", id);
  const c = document.createElementNS(NS, "circle");
  c.setAttribute("cx", String(size / 2));
  c.setAttribute("cy", String(size / 2));
  c.setAttribute("r", String(size / 2));
  clip.appendChild(c);
  defs.appendChild(clip);
  return id;
}

function appendSvgAvatar(svg, slug, x, y, size, seriesItem, color) {
  const NS = "http://www.w3.org/2000/svg";
  const meta = insightsPersonMeta(slug, seriesItem);
  const g = document.createElementNS(NS, "g");
  g.setAttribute("class", "stance-chart-avatar");
  g.setAttribute("transform", `translate(${x - size / 2}, ${y - size / 2})`);

  const ring = document.createElementNS(NS, "circle");
  ring.setAttribute("cx", String(size / 2));
  ring.setAttribute("cy", String(size / 2));
  ring.setAttribute("r", String(size / 2 + 1.5));
  ring.setAttribute("fill", "#fff");
  ring.setAttribute("stroke", color || "#e5e7eb");
  ring.setAttribute("stroke-width", "2");
  g.appendChild(ring);

  const url = meta.avatar;
  if (url && !String(url).includes("gradient")) {
    const clipId = svgDefsAvatarClip(svg, slug, size);
    const img = document.createElementNS(NS, "image");
    img.setAttribute("href", url);
    img.setAttribute("width", String(size));
    img.setAttribute("height", String(size));
    img.setAttribute("clip-path", `url(#${clipId})`);
    img.setAttribute("preserveAspectRatio", "xMidYMid slice");
    g.appendChild(img);
  } else {
    const bg = document.createElementNS(NS, "circle");
    bg.setAttribute("cx", String(size / 2));
    bg.setAttribute("cy", String(size / 2));
    bg.setAttribute("r", String(size / 2));
    bg.setAttribute("fill", color || avatarGradient(slug));
    g.appendChild(bg);
    const t = document.createElementNS(NS, "text");
    t.setAttribute("x", String(size / 2));
    t.setAttribute("y", String(size / 2 + 4));
    t.setAttribute("text-anchor", "middle");
    t.setAttribute("class", "stance-chart-avatar-text");
    t.textContent = initials(meta.name);
    g.appendChild(t);
  }
  svg.appendChild(g);
  return g;
}




function clusterByScore(items, threshold) {
  const clusters = [];
  for (const item of items) {
    let placed = false;
    for (const cluster of clusters) {
      if (Math.abs(cluster.score - item.score) <= threshold) {
        cluster.items.push(item);
        cluster.score = cluster.items.reduce((s, it) => s + it.score, 0) / cluster.items.length;
        placed = true;
        break;
      }
    }
    if (!placed) clusters.push({ score: item.score, items: [item] });
  }
  return clusters;
}

function clusterStancePoints(items, threshold) {
  const clusters = [];
  for (const item of items) {
    let placed = false;
    for (const cluster of clusters) {
      if (Math.abs(cluster.y - item.y) <= threshold) {
        cluster.items.push(item);
        cluster.y = cluster.items.reduce((s, it) => s + it.y, 0) / cluster.items.length;
        placed = true;
        break;
      }
    }
    if (!placed) clusters.push({ y: item.y, items: [item] });
  }
  return clusters;
}

function stanceSmoothPathD(coords) {
  if (!coords.length) return "";
  if (coords.length === 1) return `M ${coords[0][0]} ${coords[0][1]}`;
  if (coords.length === 2) {
    return `M ${coords[0][0]} ${coords[0][1]} L ${coords[1][0]} ${coords[1][1]}`;
  }
  let d = `M ${coords[0][0]} ${coords[0][1]}`;
  for (let i = 0; i < coords.length - 1; i++) {
    const p0 = coords[Math.max(0, i - 1)];
    const p1 = coords[i];
    const p2 = coords[i + 1];
    const p3 = coords[Math.min(coords.length - 1, i + 2)];
    const cp1x = p1[0] + (p2[0] - p0[0]) / 6;
    const cp1y = p1[1] + (p2[1] - p0[1]) / 6;
    const cp2x = p2[0] - (p3[0] - p1[0]) / 6;
    const cp2y = p2[1] - (p3[1] - p1[1]) / 6;
    d += ` C ${cp1x} ${cp1y} ${cp2x} ${cp2y} ${p2[0]} ${p2[1]}`;
  }
  return d;
}

function phaseCoordsForSlug(points, slug, xAt, yAt) {
  const coords = [];
  points.forEach((pt, i) => {
    const score = pt.scores?.[slug];
    if (score == null) return;
    coords.push([xAt(i), yAt(score)]);
  });
  return coords;
}

function closeStancePhaseModal() {
  const modal = document.getElementById("stancePhaseModal");
  if (!modal) return;
  modal.classList.remove("open");
  modal.setAttribute("aria-hidden", "true");
}

function openStancePhaseModal(pt, series, chart) {
  const modal = document.getElementById("stancePhaseModal");
  const body = document.getElementById("stancePhaseModalBody");
  const title = document.getElementById("stancePhaseModalTitle");
  if (!modal || !body || !title) return;

  const opinions = pt.opinions || {};
  const threshold = chart.overlap_threshold || 8;
  const aligned = pt.aligned !== false && (pt.max_gap ?? 99) <= threshold;

  title.textContent = pt.label || "階段意見";
  body.innerHTML = "";

  const status = document.createElement("div");
  status.className = aligned ? "stance-phase-modal-status stance-phase-modal-status--aligned" : "stance-phase-modal-status stance-phase-modal-status--split";
  status.textContent = aligned ? "此階段：意見一致" : "此階段：意見分歧";
  body.appendChild(status);

  if (chart.topic) {
    const topic = document.createElement("p");
    topic.className = "stance-phase-modal-topic";
    topic.textContent = chart.topic;
    body.appendChild(topic);
  }

  let hasAny = false;
  for (const s of series) {
    const slug = s.person_slug || "";
    if (!slug) continue;
    const op = opinions[slug];
    const score = pt.scores?.[slug];
    if (!op && score == null) continue;
    hasAny = true;

    const card = document.createElement("div");
    card.className = "stance-opinion-card";
    const head = document.createElement("div");
    head.className = "stance-opinion-head";
    head.appendChild(
      avatarEl(op?.speaker || s.name_zh || slug, "avatar sm", slug, op?.avatar_url || s.avatar_url || personAvatarUrl(slug))
    );
    const meta = document.createElement("div");
    meta.className = "stance-opinion-meta";
    const name = document.createElement("strong");
    name.textContent = op?.speaker || s.name_zh || slug;
    meta.appendChild(name);
    if (score != null) {
      const sc = document.createElement("span");
      sc.className = "stance-opinion-score";
      sc.textContent = `立場指數 ${Math.round(score)}`;
      meta.appendChild(sc);
    }
    head.appendChild(meta);
    card.appendChild(head);
    const text = document.createElement("p");
    text.className = "stance-opinion-quote";
    text.textContent = op?.quote || op?.summary || "（此階段無發言摘錄）";
    card.appendChild(text);
    body.appendChild(card);
  }

  if (!hasAny) {
    const empty = document.createElement("p");
    empty.className = "insights-empty";
    empty.textContent = "此階段尚無可顯示的發言內容";
    body.appendChild(empty);
  }

  modal.setAttribute("aria-hidden", "false");
  requestAnimationFrame(() => modal.classList.add("open"));
}


function openTimelineDetailModal(item, chart) {
  const modal = document.getElementById("stancePhaseModal");
  const body = document.getElementById("stancePhaseModalBody");
  const title = document.getElementById("stancePhaseModalTitle");
  if (!modal || !body || !title) return;

  const slug = item.person_slug || "";
  const meta = insightsPersonMeta(slug, item);
  title.textContent = `${item.name_zh || meta.name} · 第 ${item.step} 則`;
  body.innerHTML = "";

  const head = document.createElement("div");
  head.className = "stance-opinion-head";
  head.appendChild(
    avatarEl(item.name_zh || meta.name, "avatar sm", slug, item.avatar_url || meta.avatar || personAvatarUrl(slug))
  );
  const metaBox = document.createElement("div");
  metaBox.className = "stance-opinion-meta";
  const name = document.createElement("strong");
  name.textContent = item.name_zh || meta.name;
  metaBox.appendChild(name);
  const tags = document.createElement("span");
  tags.className = "stance-opinion-score";
  tags.textContent = `${item.phase_label || item.phase || ""}${item.score != null ? ` · 立場 ${Math.round(item.score)}` : ""}`;
  metaBox.appendChild(tags);
  head.appendChild(metaBox);
  body.appendChild(head);

  const hl = document.createElement("p");
  hl.className = "stance-timeline-detail-highlight";
  hl.textContent = item.highlight || item.summary || "";
  body.appendChild(hl);

  const full = document.createElement("p");
  full.className = "stance-opinion-quote";
  full.textContent = item.quote || "（無完整發言）";
  body.appendChild(full);

  if (chart?.topic) {
    const topic = document.createElement("p");
    topic.className = "stance-phase-modal-topic";
    topic.textContent = chart.topic;
    body.appendChild(topic);
  }

  modal.setAttribute("aria-hidden", "false");
  requestAnimationFrame(() => modal.classList.add("open"));
}


function stancePhaseLabel(phase) {
  const map = { opening: "開場", debate: "辯論", conclusion: "總結", discussion: "討論" };
  return map[phase] || phase || "討論";
}

/** 依本場發言分數範圍拉開縱向距離，立場越接近高度越相近 */
function stanceYFromScore(score, timeline, plotH, padT, cardH) {
  const scores = timeline.map((t) => Number(t.score ?? 50));
  let min = Math.min(...scores);
  let max = Math.max(...scores);
  let span = max - min;
  const minSpan = 32;
  if (span < minSpan) {
    const mid = (min + max) / 2;
    min = Math.max(0, mid - minSpan / 2);
    max = Math.min(100, mid + minSpan / 2);
    span = max - min || 1;
  }
  const s = Math.max(min, Math.min(max, Number(score ?? 50)));
  const t = (s - min) / span;
  const minY = padT + cardH / 2;
  const maxY = padT + plotH - cardH / 2;
  return minY + (1 - t) * (maxY - minY);
}

function resolveStanceBubbleYs(entries, timeline, plotH, padT, cardH) {
  return entries.map((e) => ({
    ...e,
    y: stanceYFromScore(e.item.score, timeline, plotH, padT, cardH),
  }));
}

function buildStanceBubbleCard(item, color, chart) {
  const card = document.createElement("button");
  card.type = "button";
  card.className = "stance-bubble-card";
  card.style.setProperty("--bubble-accent", color);
  card.setAttribute("aria-label", `${item.name_zh || ""} 第 ${item.step} 則`);

  card.appendChild(
    avatarEl(item.name_zh, "avatar", item.person_slug, item.avatar_url || personAvatarUrl(item.person_slug))
  );

  const textCol = document.createElement("div");
  textCol.className = "stance-bubble-text";

  const name = document.createElement("span");
  name.className = "stance-bubble-name";
  name.textContent = item.name_zh || item.label || "";
  textCol.appendChild(name);

  const hl = document.createElement("p");
  hl.className = "stance-bubble-highlight";
  hl.textContent = item.highlight || item.summary || "—";
  textCol.appendChild(hl);

  card.appendChild(textCol);
  card.addEventListener("click", () => openTimelineDetailModal(item, chart));
  return card;
}

function renderStanceChart(chart) {
  const host = document.getElementById("stanceChartHost");
  const legend = document.getElementById("stanceGapLegend");
  if (!host || !legend) return;

  const timeline = [...(chart.timeline || chart.trajectory || [])].sort((a, b) => {
    const sa = a.step ?? 0;
    const sb = b.step ?? 0;
    if (sa !== sb) return sa - sb;
    return String(a.person_slug || "").localeCompare(String(b.person_slug || ""));
  });
  const series = chart.series || [];

  if (!timeline.length) {
    host.innerHTML = '<p class="insights-empty">尚無名人發言紀錄</p>';
    legend.innerHTML = "";
    return;
  }

  const slugColor = {};
  series.forEach((s, i) => {
    if (s.person_slug) slugColor[s.person_slug] = INSIGHTS_LINE_COLORS[i % INSIGHTS_LINE_COLORS.length];
  });

  const CARD_W = 196;
  const CARD_H = 52;
  const COL_GAP = 12;
  const pad = { l: 44, r: 20, t: 12, b: 24 };
  const plotH = 300;
  const plotW = Math.max(
    (host.clientWidth || 320) - 8,
    pad.l + timeline.length * (CARD_W + COL_GAP) + pad.r
  );

  const xAt = (idx) => pad.l + idx * (CARD_W + COL_GAP) + CARD_W / 2;

  const entries = timeline.map((item, idx) => ({
    item,
    idx,
    x: xAt(idx),
  }));
  const laid = resolveStanceBubbleYs(entries, timeline, plotH, pad.t, CARD_H);

  const wrap = document.createElement("div");
  wrap.className = "stance-matrix-wrap stance-matrix-wrap--map";

  const toolbar = document.createElement("div");
  toolbar.className = "stance-matrix-toolbar";
  toolbar.innerHTML = `<span class="stance-matrix-toolbar-title">發言重點</span><span class="stance-matrix-toolbar-meta">${timeline.length} 則 · 左右時間 · 上下立場</span>`;
  wrap.appendChild(toolbar);

  const scrollOuter = document.createElement("div");
  scrollOuter.className = "stance-matrix-scroll-outer";

  const scroll = document.createElement("div");
  scroll.className = "stance-matrix-scroll";

  const plot = document.createElement("div");
  plot.className = "stance-matrix-plot stance-matrix-plot--map";
  plot.style.width = `${plotW}px`;
  plot.style.height = `${pad.t + plotH + pad.b}px`;

  const axisRail = document.createElement("div");
  axisRail.className = "stance-matrix-axis-rail";
  axisRail.innerHTML = `
    <span class="stance-matrix-axis-label stance-matrix-axis-label--top">${escapeHtml(chart.axis_label_high || "較積極")}</span>
    <span class="stance-matrix-axis-label stance-matrix-axis-label--sim">相近</span>
    <span class="stance-matrix-axis-label stance-matrix-axis-label--bottom">${escapeHtml(chart.axis_label_low || "較保守")}</span>`;
  plot.appendChild(axisRail);

  for (let g = 0; g <= 4; g++) {
    const gy = pad.t + (g / 4) * plotH;
    const grid = document.createElement("div");
    grid.className = "stance-matrix-gridline";
    grid.style.top = `${gy}px`;
    plot.appendChild(grid);
  }

  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", "stance-matrix-flow");
  svg.setAttribute("width", String(plotW));
  svg.setAttribute("height", String(pad.t + plotH + pad.b));
  if (laid.length >= 2) {
    const d = laid.map((p, i) => `${i ? "L" : "M"} ${p.x} ${p.y}`).join(" ");
    const path = document.createElementNS(NS, "path");
    path.setAttribute("class", "stance-matrix-flow-path");
    path.setAttribute("d", d);
    svg.appendChild(path);
  }
  plot.appendChild(svg);

  laid.forEach(({ item, idx, x, y }) => {
    const color = slugColor[item.person_slug] || "#b8860b";
    const card = buildStanceBubbleCard(item, color, chart);
    card.style.left = `${x - CARD_W / 2}px`;
    card.style.top = `${y - CARD_H / 2}px`;
    card.style.width = `${CARD_W}px`;
    plot.appendChild(card);

    const tick = document.createElement("div");
    tick.className = "stance-matrix-tick";
    tick.style.left = `${x - CARD_W / 2}px`;
    tick.style.width = `${CARD_W}px`;
    tick.style.top = `${pad.t + plotH + 6}px`;
    tick.textContent = `第 ${item.step ?? idx + 1} 則`;
    plot.appendChild(tick);
  });

  scroll.appendChild(plot);
  scrollOuter.appendChild(scroll);
  wrap.appendChild(scrollOuter);

  const hint = document.createElement("p");
  hint.className = "stance-matrix-hint";
  hint.innerHTML =
    '<span class="stance-matrix-hint-arrow">←</span> 橫向＝發言先後 · 縱向＝立場高低（越接近越相似） <span class="stance-matrix-hint-arrow">→</span>';
  wrap.appendChild(hint);

  host.innerHTML = "";
  host.appendChild(wrap);

  legend.innerHTML = "";
  const seriesLegend = document.createElement("div");
  seriesLegend.className = "stance-series-legend";
  series.forEach((s) => {
    const el = document.createElement("div");
    el.className = "stance-series-item";
    const chip = document.createElement("span");
    chip.className = "stance-series-chip";
    chip.appendChild(
      avatarEl(s.name_zh || s.person_slug, "avatar xs", s.person_slug, s.avatar_url || personAvatarUrl(s.person_slug))
    );
    const label = document.createElement("span");
    label.textContent = s.name_zh || s.person_slug || "名人";
    el.appendChild(chip);
    el.appendChild(label);
    seriesLegend.appendChild(el);
  });
  legend.appendChild(seriesLegend);

  const note = document.createElement("div");
  note.className = "stance-gap-chip stance-gap-chip--info";
  note.textContent = "卡片樣式對應各名人色 · 點擊閱讀完整發言";
  legend.appendChild(note);
}

