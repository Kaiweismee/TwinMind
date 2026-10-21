/* js/insights.js */
const INSIGHTS_LINE_COLORS = ["#6366f1", "#ec4899", "#0ea5e9", "#f59e0b", "#10b981", "#8b5cf6"];
// 預設使用 live 增量更新，避免心智圖每次都大幅重算。
// 手動按「刷新」時才會走 AI 深度分析（refresh=1）。
const INSIGHTS_PREFER_AI = false;
let insightsOpen = false;
let insightsFetchTimer = null;
let insightsInFlight = false;
let lastInsightsMsgCount = 0;
const MIND_MAP_HISTORY_LIMIT = 90;
const mindMapHistoryBySession = new Map();
const mindMapLatestBySession = new Map();
const mindMapPreviewIndexBySession = new Map();

function cloneJsonSafe(value) {
  if (typeof structuredClone === "function") return structuredClone(value);
  return JSON.parse(JSON.stringify(value));
}

function hasMindMapChildren(mind) {
  return !!(mind && Array.isArray(mind.children) && mind.children.length);
}

function getMindMapHistory(sessionId) {
  if (!sessionId) return [];
  if (!mindMapHistoryBySession.has(sessionId)) {
    mindMapHistoryBySession.set(sessionId, []);
  }
  return mindMapHistoryBySession.get(sessionId);
}

function setMindMapPreviewIndex(sessionId, idx) {
  if (!sessionId) return;
  if (idx == null || idx < 0) {
    mindMapPreviewIndexBySession.delete(sessionId);
    return;
  }
  mindMapPreviewIndexBySession.set(sessionId, idx);
}

function getMindMapPreviewIndex(sessionId) {
  if (!sessionId) return null;
  const idx = mindMapPreviewIndexBySession.get(sessionId);
  return Number.isInteger(idx) ? idx : null;
}

function mindMapLeafCount(mind) {
  const branches = Array.isArray(mind?.children) ? mind.children : [];
  let leaves = 0;
  for (const b of branches) {
    leaves += Array.isArray(b?.children) ? b.children.length : 0;
  }
  return leaves;
}

function upsertMindMapHistory(sessionId, mind, messageCount = 0) {
  if (!sessionId || !hasMindMapChildren(mind)) return;
  const history = getMindMapHistory(sessionId);
  const snapshot = {
    message_count: Number(messageCount) || 0,
    branch_count: Array.isArray(mind.children) ? mind.children.length : 0,
    leaf_count: mindMapLeafCount(mind),
    mind_map: cloneJsonSafe(mind),
  };

  const sameMsgIdx =
    snapshot.message_count > 0
      ? history.findIndex((h) => (h.message_count || 0) === snapshot.message_count)
      : -1;
  if (sameMsgIdx >= 0) {
    history[sameMsgIdx] = snapshot;
  } else {
    history.push(snapshot);
  }

  if (history.length > MIND_MAP_HISTORY_LIMIT) {
    history.splice(0, history.length - MIND_MAP_HISTORY_LIMIT);
  }
}

function getActiveMindMapForSession(sessionId, fallbackMind = {}) {
  const history = getMindMapHistory(sessionId);
  const previewIdx = getMindMapPreviewIndex(sessionId);
  if (
    previewIdx != null &&
    previewIdx >= 0 &&
    previewIdx < history.length &&
    hasMindMapChildren(history[previewIdx]?.mind_map)
  ) {
    return history[previewIdx].mind_map;
  }
  return mindMapLatestBySession.get(sessionId) || fallbackMind;
}

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
  if (mind) mind.innerHTML = '<p class="insights-empty">討論進行中，重點會自動更新…</p>';
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
    lastInsightsMsgCount = data.message_count || 0;
    renderInsights(data.insights || {});
  } catch (err) {
    const mind = document.getElementById("mindMapHost");
    if (mind) mind.innerHTML = `<p class="insights-empty">${escapeHtml(err.message || "無法載入圖譜")}</p>`;
  } finally {
    insightsInFlight = false;
    refreshBtn?.classList.remove("spinning");
  }
}

function measureTextWidth(text, fontSize = 11, weight = 400) {
  const c = measureTextWidth._c || (measureTextWidth._c = document.createElement("canvas"));
  const ctx = c.getContext("2d");
  ctx.font = `${weight} ${fontSize}px -apple-system, BlinkMacSystemFont, "PingFang TC", sans-serif`;
  return ctx.measureText(text).width;
}

function renderInsights(insights) {
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
    if (hasMindMapChildren(insights.mind_map)) {
      mindMapLatestBySession.set(currentSessionId, cloneJsonSafe(insights.mind_map));
      upsertMindMapHistory(currentSessionId, insights.mind_map, lastInsightsMsgCount);
    }
    const history = getMindMapHistory(currentSessionId);
    const idx = getMindMapPreviewIndex(currentSessionId);
    if (idx != null && idx >= history.length - 1) {
      // 停在最後一格時，自動跟著最新版本走。
      setMindMapPreviewIndex(currentSessionId, null);
    }
  }
  try {
    const mindToRender = getActiveMindMapForSession(currentSessionId, insights.mind_map || {});
    renderMindMap(mindToRender || {});
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




const MIND_MAP_BRANCH_THEMES = [
  { fill: "#dbeafe", stroke: "#2563eb", icon: "★" },
  { fill: "#dcfce7", stroke: "#16a34a", icon: "⚙" },
  { fill: "#fef9c3", stroke: "#ca8a04", icon: "💡" },
  { fill: "#fce7f3", stroke: "#db2777", icon: "♥" },
  { fill: "#ede9fe", stroke: "#7c3aed", icon: "⚠" },
  { fill: "#ccfbf1", stroke: "#0d9488", icon: "➤" },
  { fill: "#ffedd5", stroke: "#ea580c", icon: "◆" },
  { fill: "#e0e7ff", stroke: "#4f46e5", icon: "●" },
];



function mindMapWobble(seed, amp = 3) {
  const h = Math.sin(seed * 12.9898 + seed * 78.233) * 43758.5453;
  return (h - Math.floor(h) - 0.5) * 2 * amp;
}

function sketchCurvePath(x1, y1, x2, y2, seed = 0) {
  const mx = (x1 + x2) / 2 + mindMapWobble(seed, 8);
  const my = (y1 + y2) / 2 + mindMapWobble(seed + 1, 8);
  const c1x = x1 + (mx - x1) * 0.55 + mindMapWobble(seed + 2, 4);
  const c1y = y1 + (my - y1) * 0.55 + mindMapWobble(seed + 3, 4);
  const c2x = mx + (x2 - mx) * 0.45 + mindMapWobble(seed + 4, 4);
  const c2y = my + (y2 - my) * 0.45 + mindMapWobble(seed + 5, 4);
  return `M ${x1.toFixed(1)} ${y1.toFixed(1)} C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${x2.toFixed(1)} ${y2.toFixed(1)}`;
}

function splitMindMapTitle(text, maxLen = 11) {
  const s = String(text || "").trim();
  if (s.length <= maxLen) return [s];
  const mid = Math.ceil(s.length / 2);
  let split = mid;
  for (let i = mid; i < s.length && i < mid + 5; i++) {
    if (/[，、與和及\s]/.test(s[i])) {
      split = i + 1;
      break;
    }
  }
  return [s.slice(0, split).trim(), s.slice(split).trim()].filter(Boolean);
}

function cloudPath(cx, cy, w, h) {
  const x = cx - w / 2;
  const y = cy - h / 2;
  return [
    `M ${x + w * 0.2} ${y + h * 0.55}`,
    `C ${x + w * 0.05} ${y + h * 0.2}, ${x + w * 0.35} ${y + h * 0.05}, ${x + w * 0.5} ${y + h * 0.18}`,
    `C ${x + w * 0.62} ${y - h * 0.02}, ${x + w * 0.82} ${y + h * 0.08}, ${x + w * 0.88} ${y + h * 0.32}`,
    `C ${x + w * 1.02} ${y + h * 0.52}, ${x + w * 0.88} ${y + h * 0.82}, ${x + w * 0.62} ${y + h * 0.88}`,
    `C ${x + w * 0.42} ${y + h * 0.98}, ${x + w * 0.18} ${y + h * 0.82}, ${x + w * 0.2} ${y + h * 0.55}`,
    "Z",
  ].join(" ");
}

const MIND_MAP_CARD_H = 52;
const MIND_MAP_CARD_GAP = 12;

function layoutSectorMindMap(mind, hostW) {
  const branches = (mind.children || []).slice(0, hostW < 340 ? 4 : 6);
  const n = Math.max(branches.length, 1);
  const sectorWidth = (2 * Math.PI) / n;
  const branchR = hostW < 760 ? 88 : 98;
  const cardW = Math.min(168, Math.max(116, hostW * 0.36));
  const baseCardH = MIND_MAP_CARD_H + 6;
  const baseDist = branchR + 92;
  const maxFan = sectorWidth * 0.68;

  const rootLabel = mind.title || "討論主題";
  const rootW = Math.min(158, Math.max(110, measureTextWidth(rootLabel, 11, 700) + 38));
  const rootH = splitMindMapTitle(rootLabel).length > 1 ? 52 : 42;

  let maxReach = branchR + 40;
  const layoutBranches = branches.map((branch, i) => {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2;
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    const bx = 0 + branchR * cos;
    const by = 0 + branchR * sin;
    const branchLabel = String(branch.label || "議題");
    const branchW = Math.min(146, Math.max(96, measureTextWidth(branchLabel, 10, 700) + 34));
    const branchH = 32;

    const rawLeaves =
      branch.children?.length > 0
        ? branch.children
        : branch.person_slug || branch.speaker
          ? [branch]
          : [];

    const count = Math.min(4, rawLeaves.length);
    const leaves = rawLeaves.slice(0, 4).map((leaf, li) => {
      let leafAngle = angle;
      const speaker = leaf.speaker || "";
      const raw = String(leaf.quote || leaf.label || "");
      const quote =
        speaker && raw.includes("：")
          ? raw.split("：").slice(1).join("：").trim() || raw
          : raw;
      const approxCharsPerLine = Math.max(14, Math.floor((cardW - 26) / 7));
      const quoteLines = Math.max(1, Math.ceil((quote || "").length / approxCharsPerLine));
      const leafH = Math.min(132, Math.max(baseCardH, baseCardH + (quoteLines - 2) * 12));

      let dist = baseDist + leafH / 2;
      if (count > 1) {
        const fanT = count === 1 ? 0 : (li / (count - 1) - 0.5) * 2;
        leafAngle = angle + fanT * (maxFan / 2);
        dist = baseDist + leafH / 2 + Math.abs(fanT) * (cardW * 0.42 + 12);
      }
      const lx = dist * Math.cos(leafAngle);
      const ly = dist * Math.sin(leafAngle);
      maxReach = Math.max(maxReach, Math.hypot(lx, ly) + cardW / 2 + leafH / 2);
      return {
        x: lx,
        y: ly,
        w: cardW,
        h: leafH,
        cos: Math.cos(leafAngle),
        sin: Math.sin(leafAngle),
        speaker,
        quote,
        person_slug: leaf.person_slug || "",
      };
    });

    return {
      index: i,
      angle,
      cos,
      sin,
      x: bx,
      y: by,
      w: branchW,
      h: branchH,
      label: branchLabel,
      leaves,
    };
  });

  const size = Math.max(400, Math.ceil(maxReach * 2 + 60));
  const cx = size / 2;
  const cy = size / 2;

  layoutBranches.forEach((b) => {
    b.x += cx;
    b.y += cy;
    b.leaves.forEach((leaf) => {
      leaf.x += cx;
      leaf.y += cy;
    });
  });

  return {
    size,
    cx,
    cy,
    root: { label: rootLabel, x: cx, y: cy, w: rootW, h: rootH },
    branches: layoutBranches,
    cardW,
  };
}

function sectorMindMapBounds(layout, pad = 24) {
  let minX = layout.root.x - layout.root.w / 2;
  let maxX = layout.root.x + layout.root.w / 2;
  let minY = layout.root.y - layout.root.h / 2;
  let maxY = layout.root.y + layout.root.h / 2;
  for (const b of layout.branches) {
    minX = Math.min(minX, b.x - b.w / 2);
    maxX = Math.max(maxX, b.x + b.w / 2);
    minY = Math.min(minY, b.y - b.h / 2);
    maxY = Math.max(maxY, b.y + b.h / 2);
    for (const leaf of b.leaves) {
      minX = Math.min(minX, leaf.x - leaf.w / 2);
      maxX = Math.max(maxX, leaf.x + leaf.w / 2);
      minY = Math.min(minY, leaf.y - leaf.h / 2);
      maxY = Math.max(maxY, leaf.y + leaf.h / 2);
    }
  }
  return { minX: minX - pad, minY: minY - pad, maxX: maxX + pad, maxY: maxY + pad };
}

function appendMindMapLeafCard(svg, nodeLayer, leaf, theme, branchIndex, NS) {
  const x = leaf.x - leaf.w / 2;
  const y = leaf.y - leaf.h / 2;
  const g = document.createElementNS(NS, "g");
  g.setAttribute("class", "mind-map-leaf-card-wrap");

  const rect = document.createElementNS(NS, "rect");
  rect.setAttribute("x", String(x));
  rect.setAttribute("y", String(y));
  rect.setAttribute("width", String(leaf.w));
  rect.setAttribute("height", String(leaf.h));
  rect.setAttribute("rx", "10");
  rect.setAttribute("fill", "#fff");
  rect.setAttribute("stroke", theme.stroke);
  rect.setAttribute("stroke-width", "2");
  rect.setAttribute("class", "mind-map-leaf-card-bg");
  g.appendChild(rect);

  const fo = document.createElementNS(NS, "foreignObject");
  fo.setAttribute("x", String(x + 4));
  fo.setAttribute("y", String(y + 4));
  fo.setAttribute("width", String(leaf.w - 8));
  fo.setAttribute("height", String(leaf.h - 8));

  const row = document.createElement("div");
  row.className = "mind-map-leaf-card";
  row.style.setProperty("--leaf-accent", theme.stroke);

  if (leaf.person_slug) {
    const meta = insightsPersonMeta(leaf.person_slug);
    row.appendChild(avatarEl(meta.name, "avatar xs", leaf.person_slug, meta.avatar || ""));
  }
  const body = document.createElement("div");
  body.className = "mind-map-leaf-body";
  if (leaf.speaker) {
    const who = document.createElement("div");
    who.className = "mind-map-leaf-speaker";
    who.textContent = leaf.speaker;
    body.appendChild(who);
  }
  const q = document.createElement("div");
  q.className = "mind-map-leaf-quote";
  q.textContent = leaf.quote || "—";
  body.appendChild(q);
  row.appendChild(body);

  fo.appendChild(row);
  g.appendChild(fo);
  nodeLayer.appendChild(g);
}

let mindMapHistoryModalOpen = false;

function buildMindMapSvg(mind, hostWidth) {
  const branches = mind.children || [];
  if (!branches.length) return null;

  const hostW = Math.max(280, hostWidth || 300);
  const layout = layoutSectorMindMap(mind, hostW);
  const bounds = sectorMindMapBounds(layout, 20);
  const viewW = bounds.maxX - bounds.minX;
  const viewH = bounds.maxY - bounds.minY;

  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", "mind-map-svg mind-map-svg--radial");
  svg.setAttribute("viewBox", `${bounds.minX} ${bounds.minY} ${viewW} ${viewH}`);
  svg.setAttribute("width", "100%");
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");

  const linkLayer = document.createElementNS(NS, "g");
  const nodeLayer = document.createElementNS(NS, "g");
  const { root } = layout;

  layout.branches.forEach((branch) => {
    const theme = MIND_MAP_BRANCH_THEMES[branch.index % MIND_MAP_BRANCH_THEMES.length];
    const seed = branch.index * 19 + 5;

    const rootEdgeX = root.x + (branch.x - root.x) * 0.35;
    const rootEdgeY = root.y + (branch.y - root.y) * 0.35;
    const branchEdgeX = branch.x - (branch.x - root.x) * 0.15;
    const branchEdgeY = branch.y - (branch.y - root.y) * 0.15;

    const mainLink = document.createElementNS(NS, "path");
    mainLink.setAttribute("class", "mind-map-sketch-line");
    mainLink.setAttribute("stroke", theme.stroke);
    mainLink.setAttribute("d", sketchCurvePath(rootEdgeX, rootEdgeY, branchEdgeX, branchEdgeY, seed));
    linkLayer.appendChild(mainLink);

    branch.leaves.forEach((leaf, li) => {
      const dx = leaf.x - branch.x;
      const dy = leaf.y - branch.y;
      const len = Math.hypot(dx, dy) || 1;
      const ux = dx / len;
      const uy = dy / len;
      const fromX = branch.x + ux * (branch.w / 2 + 2);
      const fromY = branch.y + uy * (branch.h / 2 + 2);
      const toX = leaf.x - ux * (leaf.w / 2 + 4);
      const toY = leaf.y - uy * (leaf.h / 2 + 4);
      const link = document.createElementNS(NS, "path");
      link.setAttribute("class", "mind-map-sketch-line mind-map-sketch-line--leaf");
      link.setAttribute("stroke", theme.stroke);
      link.setAttribute("d", sketchCurvePath(fromX, fromY, toX, toY, seed + li * 4 + 2));
      linkLayer.appendChild(link);
      appendMindMapLeafCard(svg, nodeLayer, leaf, theme, branch.index, NS);
    });

    const bg = document.createElementNS(NS, "g");
    bg.setAttribute("class", "mind-map-branch");
    const rect = document.createElementNS(NS, "rect");
    rect.setAttribute("x", String(branch.x - branch.w / 2));
    rect.setAttribute("y", String(branch.y - branch.h / 2));
    rect.setAttribute("width", String(branch.w));
    rect.setAttribute("height", String(branch.h));
    rect.setAttribute("rx", "10");
    rect.setAttribute("fill", theme.fill);
    rect.setAttribute("stroke", theme.stroke);
    rect.setAttribute("stroke-width", "2.2");
    bg.appendChild(rect);

    const icon = document.createElementNS(NS, "text");
    icon.setAttribute("x", String(branch.x - branch.w / 2 + 11));
    icon.setAttribute("y", String(branch.y + 4));
    icon.setAttribute("class", "mind-map-branch-icon");
    icon.setAttribute("fill", theme.stroke);
    icon.textContent = theme.icon;
    bg.appendChild(icon);

    const label = document.createElementNS(NS, "text");
    label.setAttribute("x", String(branch.x - branch.w / 2 + 22));
    label.setAttribute("y", String(branch.y + 4));
    label.setAttribute("class", "mind-map-branch-label");
    label.setAttribute("fill", theme.stroke);
    label.textContent = branch.label;
    bg.appendChild(label);
    nodeLayer.appendChild(bg);
  });

  const centerG = document.createElementNS(NS, "g");
  centerG.setAttribute("class", "mind-map-center");
  const cloud = document.createElementNS(NS, "path");
  cloud.setAttribute("d", cloudPath(root.x, root.y, root.w, root.h));
  cloud.setAttribute("class", "mind-map-cloud");
  centerG.appendChild(cloud);
  const titleLines = splitMindMapTitle(root.label);
  titleLines.forEach((line, i) => {
    const t = document.createElementNS(NS, "text");
    t.setAttribute("x", String(root.x));
    t.setAttribute("y", String(root.y + (i - (titleLines.length - 1) / 2) * 13 + 4));
    t.setAttribute("text-anchor", "middle");
    t.setAttribute("class", "mind-map-center-text");
    t.textContent = line;
    centerG.appendChild(t);
  });
  nodeLayer.appendChild(centerG);

  svg.appendChild(linkLayer);
  svg.appendChild(nodeLayer);
  return svg;
}

function rerenderMindMapFromHistory() {
  if (!currentSessionId) return;
  const latest = mindMapLatestBySession.get(currentSessionId) || {};
  const activeMind = getActiveMindMapForSession(currentSessionId, latest);
  renderMindMap(activeMind || latest || {});
}

function renderMindMapHistoryLauncher(host) {
  const old = host.querySelector(".mind-map-history-launcher");
  if (old) old.remove();
  if (!currentSessionId) return;
  const history = getMindMapHistory(currentSessionId);
  if (!history || history.length < 2) return;

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "mind-map-history-launcher";
  btn.title = "預覽歷史紀錄";
  btn.setAttribute("aria-label", "預覽歷史紀錄");
  btn.textContent = "預覽";
  btn.addEventListener("click", () => {
    mindMapHistoryModalOpen = true;
    rerenderMindMapFromHistory();
  });
  host.appendChild(btn);
}

function renderMindMapHistoryModal(host) {
  const old = document.querySelector(".mind-map-history-overlay");
  if (old) old.remove();
  if (!mindMapHistoryModalOpen || !currentSessionId) return;
  const history = getMindMapHistory(currentSessionId);
  if (!history || history.length < 2) {
    mindMapHistoryModalOpen = false;
    return;
  }

  const activePreview = getMindMapPreviewIndex(currentSessionId);
  const activeIdx =
    activePreview != null && activePreview >= 0 && activePreview < history.length
      ? activePreview
      : history.length - 1;

  const overlay = document.createElement("div");
  overlay.className = "mind-map-history-overlay";
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) {
      mindMapHistoryModalOpen = false;
      rerenderMindMapFromHistory();
    }
  });

  const modal = document.createElement("div");
  modal.className = "mind-map-history-modal";
  overlay.appendChild(modal);

  const close = document.createElement("button");
  close.type = "button";
  close.className = "mind-map-history-close";
  close.textContent = "×";
  close.setAttribute("aria-label", "關閉歷史預覽");
  close.addEventListener("click", () => {
    mindMapHistoryModalOpen = false;
    rerenderMindMapFromHistory();
  });
  modal.appendChild(close);

  const head = document.createElement("div");
  head.className = "mind-map-history-head";
  const title = document.createElement("strong");
  title.textContent = "心智圖歷史";
  head.appendChild(title);
  const step = document.createElement("span");
  step.className = "mind-map-history-step";
  step.textContent = `${activeIdx + 1}/${history.length}`;
  head.appendChild(step);
  modal.appendChild(head);

  const previewHost = document.createElement("div");
  previewHost.className = "mind-map-history-preview-host";
  const previewMind = history[activeIdx]?.mind_map || {};
  const previewSvg = buildMindMapSvg(
    previewMind,
    Math.max(360, Math.round((host.clientWidth || 420) * 0.86))
  );
  if (previewSvg) {
    previewSvg.classList.add("mind-map-svg--history-preview");
    previewHost.appendChild(previewSvg);
  } else {
    previewHost.innerHTML = '<p class="insights-empty">此版本尚無心智圖</p>';
  }
  modal.appendChild(previewHost);

  const controls = document.createElement("div");
  controls.className = "mind-map-history-modal-controls";
  modal.appendChild(controls);

  const slider = document.createElement("input");
  slider.type = "range";
  slider.min = "0";
  slider.max = String(history.length - 1);
  slider.value = String(activeIdx);
  slider.className = "mind-map-history-range";
  slider.addEventListener("input", (e) => {
    const idx = Number(e.target.value) || 0;
    if (idx >= history.length - 1) {
      setMindMapPreviewIndex(currentSessionId, null);
    } else {
      setMindMapPreviewIndex(currentSessionId, idx);
    }
    rerenderMindMapFromHistory();
  });
  controls.appendChild(slider);

  const footer = document.createElement("div");
  footer.className = "mind-map-history-controls";
  const btnPrev = document.createElement("button");
  btnPrev.type = "button";
  btnPrev.className = "mind-map-history-btn";
  btnPrev.textContent = "◀";
  btnPrev.disabled = activeIdx <= 0;
  btnPrev.addEventListener("click", () => {
    const idx = Math.max(0, activeIdx - 1);
    setMindMapPreviewIndex(currentSessionId, idx);
    rerenderMindMapFromHistory();
  });
  footer.appendChild(btnPrev);

  const btnLatest = document.createElement("button");
  btnLatest.type = "button";
  btnLatest.className = "mind-map-history-btn" + (activeIdx === history.length - 1 ? " is-active" : "");
  btnLatest.textContent = "最新";
  btnLatest.addEventListener("click", () => {
    setMindMapPreviewIndex(currentSessionId, null);
    rerenderMindMapFromHistory();
  });
  footer.appendChild(btnLatest);

  const btnNext = document.createElement("button");
  btnNext.type = "button";
  btnNext.className = "mind-map-history-btn";
  btnNext.textContent = "▶";
  btnNext.disabled = activeIdx >= history.length - 1;
  btnNext.addEventListener("click", () => {
    const idx = Math.min(history.length - 1, activeIdx + 1);
    if (idx >= history.length - 1) {
      setMindMapPreviewIndex(currentSessionId, null);
    } else {
      setMindMapPreviewIndex(currentSessionId, idx);
    }
    rerenderMindMapFromHistory();
  });
  footer.appendChild(btnNext);
  controls.appendChild(footer);

  const meta = history[activeIdx] || {};
  const msgTag = document.createElement("div");
  msgTag.className = "mind-map-history-meta";
  msgTag.textContent = meta.message_count
    ? `第 ${meta.message_count} 則訊息`
    : `版本 ${activeIdx + 1}`;
  controls.appendChild(msgTag);

  document.body.appendChild(overlay);
}

function renderMindMap(mind) {
  const host = document.getElementById("mindMapHost");
  if (!host) return;
  const svg = buildMindMapSvg(mind, host.clientWidth || 300);
  host.innerHTML = "";
  if (!svg) {
    host.innerHTML = '<p class="insights-empty">尚無足夠內容產生心智圖</p>';
    renderMindMapHistoryLauncher(host);
    renderMindMapHistoryModal(host);
    return;
  }
  host.appendChild(svg);
  renderMindMapHistoryLauncher(host);
  renderMindMapHistoryModal(host);
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

