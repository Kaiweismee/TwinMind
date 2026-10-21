/* js/discover.js */
function buildCharCard(p) {
  const card = document.createElement("article");
  card.className = "char-card";
  card.appendChild(avatarEl(p.name_zh, "avatar lg", p.slug, p.avatar_url));
  const body = document.createElement("div");
  body.className = "char-card-body";
  body.innerHTML = `
    <h3>${escapeHtml(p.name_zh)}</h3>
    <div class="char-card-bio">${escapeHtml((p.bio || "數位分身").slice(0, 120))}</div>
    <div class="char-card-stats">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
      <span>${formatViews(p.doc_count)}</span>
    </div>
  `;
  card.appendChild(body);
  card.addEventListener("click", () => openPersonProfileModal(p));
  return card;
}

function openScenePreset(scene, validSlugs) {
  if (!isAuthenticated) {
    alert("請先登入後再開始場景討論");
    showAuthGate();
    return;
  }
  if (!validSlugs.length) {
    alert("此場景目前沒有可用名人，請改用手動建立");
    return;
  }
  openCreateModal({
    slugs: validSlugs,
    topic: "",
    disableTopicRecommend: true,
  });
}

let mediaLibraryItems = [];
let mediaLibraryLoaded = false;
let mediaLibraryLoading = false;
let discoverMediaRailVisible = false;

function setDiscoverMediaRailVisible(visible) {
  discoverMediaRailVisible = !!visible;
  const home = document.getElementById("discoverHome");
  const rail = document.getElementById("discoverMediaRail");
  if (!rail || !home) return;
  home.classList.toggle("media-only", discoverMediaRailVisible);
  rail.classList.toggle("hidden", !discoverMediaRailVisible);
  if (discoverMediaRailVisible) {
    loadMediaLibraryPanel(true);
  }
}

function mediaSourceLabel(source) {
  return source === "session_context" ? "聊天室參考資料" : "訓練個人資料";
}

function mediaTimeLabel(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function mediaSizeLabel(bytes) {
  const n = Number(bytes || 0);
  if (n >= 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)}MB`;
  if (n >= 1024) return `${Math.round(n / 1024)}KB`;
  return `${n}B`;
}

function renderMediaLibraryPanel() {
  const statsEl = document.getElementById("discoverMediaStats");
  const listEl = document.getElementById("discoverMediaList");
  if (!statsEl || !listEl) return;

  const imageN = mediaLibraryItems.filter((i) => (i.file || {}).kind === "image").length;
  const fileN = mediaLibraryItems.length - imageN;
  statsEl.innerHTML = `
    <span class="discover-media-chip">共 ${mediaLibraryItems.length} 筆</span>
    <span class="discover-media-chip">圖片 ${imageN}</span>
    <span class="discover-media-chip">文件 ${fileN}</span>
  `;

  if (!mediaLibraryItems.length) {
    listEl.innerHTML = '<p class="discover-media-empty">尚未上傳媒體檔案</p>';
    return;
  }

  listEl.innerHTML = "";
  const home = document.getElementById("discoverHome");
  const mediaOnlyMode = home?.classList.contains("media-only");
  const showItems = mediaOnlyMode ? mediaLibraryItems : mediaLibraryItems.slice(0, 14);
  showItems.forEach((item) => {
    const f = item.file || {};
    const card = document.createElement("article");
    card.className = "discover-media-item";
    const thumb = document.createElement("div");
    thumb.className = "discover-media-thumb";
    if (f.kind === "image" && f.url) {
      const img = document.createElement("img");
      img.src = f.url;
      img.alt = f.name || "image";
      img.loading = "lazy";
      thumb.appendChild(img);
    } else {
      thumb.textContent = "檔案";
    }
    card.appendChild(thumb);

    const body = document.createElement("div");
    body.className = "discover-media-body";
    body.innerHTML = `
      <div class="discover-media-name" title="${escapeHtml(f.name || "未命名檔案")}">${escapeHtml(f.name || "未命名檔案")}</div>
      <div class="discover-media-meta">
        ${escapeHtml(mediaSourceLabel(item.source))}<br>
        ${item.session_topic ? `主題：${escapeHtml(item.session_topic)}<br>` : ""}
        ${escapeHtml(mediaTimeLabel(item.created_at))} · ${escapeHtml(mediaSizeLabel(f.size))}
      </div>
    `;
    card.appendChild(body);
    card.addEventListener("click", () => {
      if (f.url) window.open(f.url, "_blank", "noopener");
    });
    listEl.appendChild(card);
  });
}

async function loadMediaLibraryPanel(force = false) {
  const statsEl = document.getElementById("discoverMediaStats");
  const listEl = document.getElementById("discoverMediaList");
  if (!statsEl || !listEl) return;
  if (!isAuthenticated) {
    statsEl.innerHTML = '<span class="discover-media-chip">請先登入</span>';
    listEl.innerHTML = '<p class="discover-media-empty">登入後可查看媒體庫</p>';
    return;
  }
  if (mediaLibraryLoading) return;
  if (mediaLibraryLoaded && !force) {
    renderMediaLibraryPanel();
    return;
  }
  mediaLibraryLoading = true;
  statsEl.innerHTML = '<span class="discover-media-chip">載入中…</span>';
  try {
    const data = await fetchJson("/api/media-library?limit=120");
    mediaLibraryItems = data.items || [];
    mediaLibraryLoaded = true;
    renderMediaLibraryPanel();
  } catch (e) {
    listEl.innerHTML = `<p class="discover-media-empty">${escapeHtml(e.message || "載入失敗")}</p>`;
    statsEl.innerHTML = '<span class="discover-media-chip">載入失敗</span>';
  } finally {
    mediaLibraryLoading = false;
  }
}

function renderDiscoverFeed() {
  const list = filterPersons(globalSearchQuery);
  const sorted = [...list].sort(
    (a, b) => (b.chunk_count || 0) - (a.chunk_count || 0)
  );
  const bySlug = new Map(list.map((p) => [p.slug, p]));

  const recommended = document.getElementById("recommendedRow");
  const scenes = document.getElementById("scenesRow");
  const categoryNav = document.getElementById("categoryNav");

  if (recommended) recommended.innerHTML = "";
  if (scenes) scenes.innerHTML = "";
  if (categoryNav) categoryNav.innerHTML = "";

  if (recommended) {
    if (!list.length && globalSearchQuery) {
      recommended.innerHTML = '<p class="empty discover-empty">找不到符合的角色</p>';
    } else {
      sorted.slice(0, 12).forEach((p) => recommended.appendChild(buildCharCard(p)));
    }
  }

  const slugSet = new Set(persons.map((p) => p.slug));
  for (const scene of SCENES) {
    const valid = scene.slugs.filter((s) => slugSet.has(s));
    if (valid.length < 2) continue;

    const wrap = document.createElement("div");
    wrap.className = "scene-card";
    const visual = document.createElement("div");
    visual.className = "scene-card-visual";
    if (scene.image) {
      visual.style.backgroundImage = `url("${scene.image}")`;
      visual.style.backgroundColor = "#111827";
    } else {
      visual.style.background = scene.gradient;
    }

    const title = document.createElement("div");
    title.className = "scene-card-title";
    title.textContent = scene.title;
    visual.appendChild(title);

    const subtitle = document.createElement("div");
    subtitle.className = "scene-card-subtitle";
    subtitle.textContent = scene.subtitle || "";
    visual.appendChild(subtitle);

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "scene-card-btn";
    btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg> 進入場景`;
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      openScenePreset(scene, valid);
    });
    visual.appendChild(btn);

    visual.addEventListener("click", () => {
      openScenePreset(scene, valid);
    });

    wrap.appendChild(visual);
    scenes?.appendChild(wrap);
  }

  if (categoryNav && personCategories.length) {
    const catsWithPeople = personCategories.filter((cat) =>
      (cat.slugs || []).some((slug) => bySlug.has(slug))
    );
    if (catsWithPeople.length) {
      if (!activeCategoryId || !catsWithPeople.some((c) => c.id === activeCategoryId)) {
        activeCategoryId = catsWithPeople[0].id;
      }
      catsWithPeople.forEach((cat) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = `category-nav-btn${cat.id === activeCategoryId ? " active" : ""}`;
        btn.dataset.categoryId = cat.id;
        btn.textContent = cat.title || cat.id;
        btn.addEventListener("click", () => selectCategory(cat.id));
        categoryNav.appendChild(btn);
      });
      renderCategoryPersons(bySlug);
    } else {
      renderCategoryPersons(bySlug);
    }
  } else {
    renderCategoryPersons(bySlug);
  }
  if (discoverMediaRailVisible) loadMediaLibraryPanel();
}

function selectCategory(catId) {
  activeCategoryId = catId;
  document.querySelectorAll(".category-nav-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.categoryId === catId);
  });
  const list = filterPersons(globalSearchQuery);
  renderCategoryPersons(new Map(list.map((p) => [p.slug, p])));
}

function renderCategoryPersons(bySlug) {
  const row = document.getElementById("categoryPersonRow");
  if (!row) return;
  row.innerHTML = "";
  const cat = personCategories.find((c) => c.id === activeCategoryId);
  if (!cat) return;
  const items = (cat.slugs || [])
    .map((slug) => bySlug.get(slug))
    .filter(Boolean);
  if (!items.length) {
    row.innerHTML = '<p class="empty discover-empty">此類別暫無名人</p>';
    return;
  }
  items.forEach((p) => row.appendChild(buildCharCard(p)));
}

function topicFitBySlug(slug) {
  return topicRecommendations.find((p) => p.slug === slug);
}

function fitTierLabel(p) {
  return p?.fit_tier_label || { high: "高", mid: "中", low: "低" }[p?.fit_tier] || "";
}

function fitTierClass(tier) {
  const t = tier || "low";
  return `topic-fit-tier topic-fit-tier--${t}`;
}

const TOPIC_FIT_TIER_ROWS = [
  { key: "high", title: "高契合", short: "高" },
];

function topicFitTierCounts() {
  const counts = { high: 0 };
  for (const p of topicRecommendations) {
    const t = p.fit_tier || "low";
    if (t in counts) counts[t] += 1;
  }
  return counts;
}

function pickDefaultTopicRecommendTier() {
  return "high";
}

function setTopicRecommendPanelVisible(visible) {
  const block = document.getElementById("topicRecommendBlock");
  if (!block) return;
  block.classList.toggle("hidden", !visible);
}

function setTopicRecommendPanelMessage(html, className = "topic-recommend-hint") {
  setTopicRecommendPanelVisible(true);
  const nav = document.getElementById("topicRecommendTierNav");
  const track = document.getElementById("topicRecommendTrack");
  const hint = document.querySelector(".topic-recommend-hint-text");
  if (nav) {
    nav.innerHTML = "";
    nav.classList.add("hidden");
  }
  if (track) {
    track.innerHTML = `<p class="${className}">${html}</p>`;
    track.className = "topic-recommend-row-track";
  }
  if (hint) hint.classList.toggle("hidden", true);
}

function showTopicRecommendIconPanel(text, { spinning = false } = {}) {
  setTopicRecommendPanelVisible(true);
  const nav = document.getElementById("topicRecommendTierNav");
  const track = document.getElementById("topicRecommendTrack");
  const hint = document.querySelector(".topic-recommend-hint-text");
  if (nav) {
    nav.innerHTML = "";
    nav.classList.add("hidden");
  }
  if (hint) hint.classList.add("hidden");
  if (!track) return;
  const iconClass = spinning ? "topic-recommend-spinner" : "topic-recommend-icon";
  track.className = "topic-recommend-row-track topic-recommend-loading-state";
  track.innerHTML = `
    <div class="topic-recommend-loading-wrap">
      <img src="/static/icon.png" alt="" class="${iconClass}" width="44" height="44" />
      <p class="topic-recommend-loading-text">${escapeHtml(text)}</p>
    </div>`;
}

function showTopicRecommendLoading() {
  showTopicRecommendIconPanel("正在用 AI 與資料庫分析契合度…", { spinning: true });
}

function topicRecommendMinDelay() {
  return new Promise((resolve) => {
    setTimeout(resolve, TOPIC_RECOMMEND_MIN_LOAD_MS);
  });
}

function renderTopicRecommendTierNav() {
  const nav = document.getElementById("topicRecommendTierNav");
  if (!nav) return;
  const counts = topicFitTierCounts();
  nav.classList.remove("hidden");
  nav.innerHTML = "";

  for (const rowDef of TOPIC_FIT_TIER_ROWS) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.role = "tab";
    btn.className = `topic-recommend-tier-btn topic-recommend-tier-btn--${rowDef.key}`;
    const isActive = activeTopicRecommendTier === rowDef.key;
    if (isActive) btn.classList.add("active");
    btn.setAttribute("aria-selected", isActive ? "true" : "false");
    btn.dataset.tier = rowDef.key;

    const label = document.createElement("span");
    label.className = "topic-recommend-tier-btn-label";
    label.textContent = rowDef.short;

    const count = document.createElement("span");
    count.className = "topic-recommend-tier-btn-count";
    count.textContent = String(counts[rowDef.key] ?? 0);

    btn.appendChild(label);
    btn.appendChild(count);
    btn.addEventListener("click", () => {
      activeTopicRecommendTier = rowDef.key;
      renderTopicRecommendRows();
    });
    nav.appendChild(btn);
  }
}

function buildTopicRecommendCard(p) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "topic-recommend-card";
  if (selectedSlugs.has(p.slug)) btn.classList.add("selected");
  btn.setAttribute("aria-label", `${p.name_zh || p.slug} ${fitTierLabel(p)}契合`);

  btn.appendChild(
    avatarEl(p.name_zh, "avatar", p.slug, p.avatar_url || personAvatarUrl(p.slug))
  );

  const name = document.createElement("span");
  name.className = "topic-recommend-name";
  name.textContent = p.name_zh || p.slug;
  btn.appendChild(name);

  btn.addEventListener("click", () => {
    if (selectedSlugs.has(p.slug)) selectedSlugs.delete(p.slug);
    else selectedSlugs.add(p.slug);
    updateModalSelection();
    renderTopicRecommendRows();
    renderModalPersons();
  });
  return btn;
}

function renderTopicRecommendRows() {
  const track = document.getElementById("topicRecommendTrack");
  const block = document.getElementById("topicRecommendBlock");
  const hint = document.querySelector(".topic-recommend-hint-text");
  if (!track || !block) return;
  setTopicRecommendPanelVisible(true);

  if (!topicRecommendations.length) {
    setTopicRecommendPanelMessage("尚無推薦，請手動選擇名人", "topic-recommend-empty");
    return;
  }

  if (!topicFitTierCounts()[activeTopicRecommendTier]) {
    activeTopicRecommendTier = pickDefaultTopicRecommendTier();
  }

  hint?.classList.remove("hidden");
  renderTopicRecommendTierNav();

  const group = topicRecommendations.filter(
    (p) => (p.fit_tier || "low") === activeTopicRecommendTier
  );
  const rowDef = TOPIC_FIT_TIER_ROWS.find((r) => r.key === activeTopicRecommendTier);

  track.innerHTML = "";
  track.className = `topic-recommend-row-track topic-recommend-row-track--${activeTopicRecommendTier}`;

  if (!group.length) {
    const empty = document.createElement("p");
    empty.className = "topic-recommend-row-empty";
    empty.textContent = `此主題暫無${rowDef?.title || ""}名人`;
    track.appendChild(empty);
    return;
  }

  group.forEach((p) => track.appendChild(buildTopicRecommendCard(p)));
}

function scheduleTopicRecommendations() {
  if (topicRecommendTimer) clearTimeout(topicRecommendTimer);
  topicRecommendTimer = setTimeout(() => fetchTopicRecommendations(), 280);
}

function showTopicRecommendPlaceholder() {
  topicRecommendations = [];
  activeTopicRecommendTier = "high";
  showTopicRecommendIconPanel("輸入主題推薦名人");
  renderModalPersons();
}

async function fetchTopicRecommendations() {
  const topic = (document.getElementById("roomTopic")?.value || "").trim();
  if (!document.getElementById("createModal")?.classList.contains("open")) return;

  if (topic.length < 2) {
    topicRecommendFetchId += 1;
    showTopicRecommendPlaceholder();
    return;
  }

  const fetchId = ++topicRecommendFetchId;
  showTopicRecommendLoading();

  const controller = new AbortController();
  const abortTimer = setTimeout(() => controller.abort(), 90000);

  try {
    const [data] = await Promise.all([
      fetchJson(
        `/api/persons/recommend?topic=${encodeURIComponent(topic)}&limit=41`,
        { signal: controller.signal }
      ),
      topicRecommendMinDelay(),
    ]);
    if (fetchId !== topicRecommendFetchId) return;

    topicRecommendations = data.recommendations || [];
    activeTopicRecommendTier = pickDefaultTopicRecommendTier();

    if (!topicRecommendations.length) {
      setTopicRecommendPanelMessage("尚無推薦，請手動選擇名人", "topic-recommend-empty");
      renderModalPersons();
      return;
    }

    renderTopicRecommendRows();
    renderModalPersons();
  } catch (err) {
    if (fetchId !== topicRecommendFetchId) return;
    console.error("topic recommend failed", err);
    topicRecommendations = [];
    const msg =
      err?.name === "AbortError"
        ? "AI 推薦逾時，請稍後再試或手動選擇名人"
        : err.message || "AI 推薦載入失敗";
    setTopicRecommendPanelMessage(escapeHtml(msg), "topic-recommend-error");
    renderModalPersons();
  } finally {
    clearTimeout(abortTimer);
  }
}

function renderCreateRoomAttachPreview() {
  const box = document.getElementById("createRoomAttachPreview");
  if (!box) return;
  box.innerHTML = "";
  if (!createRoomPendingFiles.length) {
    box.classList.add("hidden");
    return;
  }
  box.classList.remove("hidden");
  createRoomPendingFiles.forEach((file, idx) => {
    const chip = document.createElement("span");
    chip.className = "create-room-attach-chip";
    chip.innerHTML = `<span>${escapeHtml(file.name)}</span>`;
    const rm = document.createElement("button");
    rm.type = "button";
    rm.textContent = "×";
    rm.addEventListener("click", () => {
      createRoomPendingFiles.splice(idx, 1);
      renderCreateRoomAttachPreview();
      updateModalSelection();
    });
    chip.appendChild(rm);
    box.appendChild(chip);
  });
}

function updateModalSelection() {
  const n = selectedSlugs.size;
  const topic = (document.getElementById("roomTopic")?.value || "").trim();
  const f = createRoomPendingFiles.length;
  const countEl = document.getElementById("selectedCount");
  if (countEl) {
    countEl.textContent = f
      ? `已選 ${n} 位名人 · ${f} 個參考檔`
      : `已選 ${n} 位名人`;
  }
  document.getElementById("btnStartRoom").disabled = n < 1 || !topic;
  document.querySelectorAll(".modal-person").forEach((row) => {
    const slug = row.dataset.slug;
    const checked = selectedSlugs.has(slug);
    row.classList.toggle("selected", checked);
    const cb = row.querySelector('input[type="checkbox"]');
    if (cb) cb.checked = checked;
  });
}

function renderModalPersons() {
  const list = document.getElementById("modalPersonList");
  if (!list) return;
  list.innerHTML = "";
  const keyword = (document.getElementById("modalPersonSearch")?.value || "")
    .trim()
    .toLowerCase();
  const fitMap = new Map(topicRecommendations.map((p) => [p.slug, p]));
  const tierRank = { high: 0, mid: 1, low: 2 };

  const sorted = [...persons]
    .filter((p) => {
      if (!keyword) return true;
      const zh = (p.name_zh || "").toLowerCase();
      const en = (p.name_en || "").toLowerCase();
      const slug = (p.slug || "").toLowerCase();
      return zh.includes(keyword) || en.includes(keyword) || slug.includes(keyword);
    })
    .sort((a, b) => {
    const fa = fitMap.get(a.slug);
    const fb = fitMap.get(b.slug);
    if (fa && fb) {
      const ta = tierRank[fa.fit_tier] ?? 9;
      const tb = tierRank[fb.fit_tier] ?? 9;
      if (ta !== tb) return ta - tb;
      return (fb.topic_fit_score || 0) - (fa.topic_fit_score || 0);
    }
    if (fa) return -1;
    if (fb) return 1;
    return (a.name_zh || "").localeCompare(b.name_zh || "");
  });
  if (!sorted.length) {
    list.innerHTML = '<p class="empty">找不到符合的名人</p>';
    updateModalSelection();
    return;
  }
  for (const p of sorted) {
    const fit = fitMap.get(p.slug);
    const row = document.createElement("label");
    row.className = "modal-person";
    row.dataset.slug = p.slug;
    row.setAttribute("role", "listitem");
    if (fit?.fit_tier) row.dataset.fitTier = fit.fit_tier;

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "modal-person-checkbox";
    cb.checked = selectedSlugs.has(p.slug);
    if (cb.checked) row.classList.add("selected");
    cb.addEventListener("change", () => {
      if (cb.checked) selectedSlugs.add(p.slug);
      else selectedSlugs.delete(p.slug);
      updateModalSelection();
      if (topicRecommendations.length) renderTopicRecommendRows();
    });

    const checkWrap = document.createElement("span");
    checkWrap.className = "modal-person-check";
    checkWrap.appendChild(cb);

    const info = document.createElement("div");
    info.className = "modal-person-main";

    const head = document.createElement("div");
    head.className = "modal-person-head";

    const name = document.createElement("span");
    name.className = "modal-person-name";
    name.textContent = p.name_zh || p.slug;
    head.appendChild(name);

    if (fit?.fit_tier === "high") {
      const badge = document.createElement("span");
      badge.className = "modal-person-fit modal-person-fit--high";
      badge.textContent = "高契合";
      head.appendChild(badge);
    }

    const sub = document.createElement("span");
    sub.className = "modal-person-en";
    sub.textContent = p.name_en || "";

    info.appendChild(head);
    if (p.name_en) info.appendChild(sub);

    row.appendChild(checkWrap);
    row.appendChild(avatarEl(p.name_zh, "avatar sm", p.slug, p.avatar_url));
    row.appendChild(info);
    list.appendChild(row);
  }
  updateModalSelection();
}

function renderParticipantChips(session) {
  const box = document.getElementById("participantChips");
  if (!box) return;
  box.innerHTML = "";
  const you = document.createElement("span");
  you.className = "chip you";
  you.textContent =
    (session?.owner_label || "").trim() ||
    (typeof preferredUserLabel === "function"
      ? preferredUserLabel(profile)
      : (profile?.display_name || profile?.account_name || profile?.username || "你"));
  box.appendChild(you);
  for (const m of session.members || []) {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = m.name_zh;
    box.appendChild(chip);
  }
  const guestNames = new Set();
  for (const g of session.guests || []) {
    const name = (g.display_name || "").trim();
    if (!name || guestNames.has(name)) continue;
    guestNames.add(name);
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = name;
    box.appendChild(chip);
  }
}

