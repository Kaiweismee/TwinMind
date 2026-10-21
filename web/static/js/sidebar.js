/* js/sidebar.js */
function groupSessions(list) {
  const now = Date.now();
  const day = 24 * 60 * 60 * 1000;
  const week = 7 * day;
  const month = 30 * day;
  const pinned = [];
  const groups = { 剛才: [], 上週: [], 本月: [], 更早: [] };
  for (const s of list) {
    if (s.pinned) {
      pinned.push(s);
      continue;
    }
    const t = new Date(s.updated_at || s.created_at).getTime();
    const age = now - t;
    if (age <= day) groups["剛才"].push(s);
    else if (age <= week) groups["上週"].push(s);
    else if (age <= month) groups["本月"].push(s);
    else groups["更早"].push(s);
  }
  pinned.sort(
    (a, b) =>
      new Date(b.updated_at || b.created_at) -
      new Date(a.updated_at || a.created_at)
  );
  return { 已釘選: pinned, ...groups };
}

async function toggleSessionPin(sessionId, pinned, ev) {
  if (ev) {
    ev.preventDefault();
    ev.stopPropagation();
  }
  try {
    await fetchJson(
      `/api/sessions/${sessionId}/pin`,
      {
        method: "PATCH",
        body: JSON.stringify({ pinned }),
      },
      sessionId
    );
    const s = sessions.find((x) => x.id === sessionId);
    if (s) s.pinned = pinned;
    renderHistory(document.getElementById("historySearch")?.value || "");
  } catch (e) {
    alert(e.message);
  }
}

const PIN_ICON_SVG = `<svg class="history-pin-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z"/></svg>`;
const DELETE_ICON_SVG = `<svg class="history-delete-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 3h6l1 2h4v2H4V5h4l1-2zm-2 6h10l-1 10a2 2 0 01-2 2h-4a2 2 0 01-2-2L7 9z"/></svg>`;

async function deleteSession(sessionId, ev) {
  if (ev) {
    ev.preventDefault();
    ev.stopPropagation();
  }
  const s = sessions.find((x) => x.id === sessionId);
  if (!isAuthenticated) {
    alert("請先登入後再刪除聊天室");
    return;
  }
  const topic = s ? sessionTopic(s) : "這個聊天室";
  const firstAsk = `要刪除「${topic}」嗎？`;
  const secondAsk = "刪除後無法復原，確定要刪除嗎？";
  if (!window.confirm(firstAsk)) return;
  if (!window.confirm(secondAsk)) return;

  try {
    await fetchJson(
      `/api/sessions/${sessionId}`,
      { method: "DELETE" },
      null
    );
    unregisterSession(sessionId);
    sessions = sessions.filter((x) => x.id !== sessionId);
    if (currentSessionId === sessionId) {
      stopAutoDiscussion();
      currentSessionId = null;
      currentSession = null;
      showDiscover();
    } else {
      renderHistory(document.getElementById("historySearch")?.value || "");
    }
    await loadSessions();
  } catch (e) {
    alert(e.message);
  }
}

function isPersonChatActive(slug) {
  return (
    twinChatVisible &&
    twinChatMode === "person" &&
    twinChatPerson?.slug === slug
  );
}

function historyItemsMerged() {
  const roomItems = sessions.map((s) => ({ ...s, kind: "session" }));
  const personItems = (personChatThreads || []).map((t) => ({ ...t, kind: "person_chat" }));
  return [...roomItems, ...personItems].sort((a, b) => {
    const ta = Date.parse(a.updated_at || a.created_at || 0);
    const tb = Date.parse(b.updated_at || b.created_at || 0);
    return tb - ta;
  });
}

async function deletePersonChatThread(personSlug, ev) {
  if (ev) {
    ev.preventDefault();
    ev.stopPropagation();
  }
  const thread = (personChatThreads || []).find((t) => t.person_slug === personSlug);
  const name = thread?.person_name_zh || personSlug;
  if (!window.confirm(`要刪除與「${name}」的對話紀錄嗎？`)) return;
  if (!window.confirm("刪除後無法復原，確定要刪除嗎？")) return;
  try {
    await fetchJson(`/api/person-chat/threads/${encodeURIComponent(personSlug)}`, {
      method: "DELETE",
    });
    personChatThreads = (personChatThreads || []).filter((t) => t.person_slug !== personSlug);
    if (isPersonChatActive(personSlug)) {
      showDiscover();
      twinChatMode = "twin";
      twinChatPerson = null;
    }
    renderHistory(document.getElementById("historySearch")?.value || "");
  } catch (e) {
    alert(e.message);
  }
}

function appendHistoryItem(el, s) {
  if (s.kind === "person_chat") {
    appendPersonChatHistoryItem(el, s);
    return;
  }

  const isPinned = !!s.pinned;

  const row = document.createElement("div");
  row.className =
    "history-row" +
    (s.id === currentSessionId ? " active" : "") +
    (isPinned ? " pinned" : "");

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "history-item";

  const card = document.createElement("div");
  card.className = "history-card";

  const titleRow = document.createElement("div");
  titleRow.className = "history-title-row";

  const meta = document.createElement("div");
  meta.className = "history-meta";
  const lock = s.has_password
    ? '<span class="history-lock" title="需密碼加入">🔒</span> '
    : "";
  meta.innerHTML = `<div class="name">${lock}${escapeHtml(sessionTopic(s))}</div>`;
  titleRow.appendChild(meta);
  card.appendChild(titleRow);

  const pinBtn = document.createElement("button");
  pinBtn.type = "button";
  pinBtn.className = "history-pin-btn" + (isPinned ? " is-pinned" : "");
  pinBtn.title = isPinned ? "取消釘選" : "釘選";
  pinBtn.setAttribute("aria-label", pinBtn.title);
  pinBtn.innerHTML = PIN_ICON_SVG;
  pinBtn.addEventListener("click", (e) => toggleSessionPin(s.id, !isPinned, e));
  pinBtn.classList.add("history-pin-btn--corner");
  card.appendChild(pinBtn);

  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.className = "history-delete-btn history-delete-btn--corner";
  delBtn.title = "刪除";
  delBtn.setAttribute("aria-label", "刪除");
  delBtn.innerHTML = DELETE_ICON_SVG;
  delBtn.addEventListener("click", (e) => deleteSession(s.id, e));
  card.appendChild(delBtn);

  const corner = document.createElement("div");
  corner.className = "history-avatars-corner";
  corner.appendChild(buildAvatarStack(s.members || [], 3));
  card.appendChild(corner);

  btn.appendChild(card);
  btn.addEventListener("click", () => openSession(s.id));
  row.appendChild(btn);
  el.appendChild(row);
}

function appendPersonChatHistoryItem(el, t) {
  const slug = t.person_slug || "";
  const active = isPersonChatActive(slug);

  const row = document.createElement("div");
  row.className = "history-row" + (active ? " active" : "");

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "history-item";

  const card = document.createElement("div");
  card.className = "history-card history-card--person";

  const meta = document.createElement("div");
  meta.className = "history-meta";
  meta.innerHTML = `<div class="name">${escapeHtml(sessionTopic(t))}</div>`;
  card.appendChild(meta);

  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.className = "history-delete-btn history-delete-btn--corner";
  delBtn.title = "刪除";
  delBtn.setAttribute("aria-label", "刪除");
  delBtn.innerHTML = DELETE_ICON_SVG;
  delBtn.addEventListener("click", (e) => deletePersonChatThread(slug, e));
  card.appendChild(delBtn);

  const corner = document.createElement("div");
  corner.className = "history-avatars-corner";
  corner.appendChild(
    buildAvatarStack(
      t.members || [
        {
          person_slug: slug,
          name_zh: t.person_name_zh || slug,
          avatar_url: t.avatar_url || "",
        },
      ],
      1
    )
  );
  card.appendChild(corner);

  btn.appendChild(card);
  btn.addEventListener("click", () => {
    const person =
      persons.find((p) => p.slug === slug) ||
      {
        slug,
        name_zh: t.person_name_zh || slug,
        avatar_url: t.avatar_url || "",
        bio: "",
      };
    showPersonChat(person);
  });
  row.appendChild(btn);
  el.appendChild(row);
}

function sessionTopic(s) {
  if (s.kind === "person_chat") {
    return (s.topic || s.person_name_zh || "").trim() || "名人對話";
  }
  return (s.topic || "").trim() || "未命名討論";
}

function stackAvatarItem(m) {
  const name = m?.name_zh || "?";
  const slug = m?.person_slug || "";
  const url = m?.avatar_url || personAvatarUrl(slug);
  if (url) {
    const img = document.createElement("img");
    img.className = "stack-item";
    img.src = url;
    img.alt = name;
    img.loading = "lazy";
    img.onerror = () => {
      const fb = document.createElement("div");
      fb.className = "stack-item";
      fb.textContent = initials(name);
      if (slug) fb.style.background = avatarGradient(slug);
      img.replaceWith(fb);
    };
    return img;
  }
  const d = document.createElement("div");
  d.className = "stack-item";
  d.textContent = initials(name);
  if (slug) d.style.background = avatarGradient(slug);
  return d;
}

function buildAvatarStack(members, maxShow = 4) {
  const wrap = document.createElement("div");
  wrap.className = "avatar-stack";
  const list = members || [];
  if (!list.length) {
    const d = document.createElement("div");
    d.className = "stack-item";
    d.textContent = "?";
    wrap.appendChild(d);
    return wrap;
  }
  for (const m of list.slice(0, maxShow)) {
    wrap.appendChild(stackAvatarItem(m));
  }
  if (list.length > maxShow) {
    const more = document.createElement("div");
    more.className = "stack-item";
    more.textContent = `+${list.length - maxShow}`;
    more.style.background = "#9ca3af";
    wrap.appendChild(more);
  }
  return wrap;
}

function renderHistory(filter = "") {
  const el = document.getElementById("historyList");
  el.innerHTML = "";
  const q = filter.trim().toLowerCase();
  const filtered = historyItemsMerged().filter((s) => {
    if (!q) return true;
    const hay = [
      s.topic,
      s.members_label,
      s.person_name_zh,
      s.last_message,
      s.person_slug,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return hay.includes(q);
  });

  if (!filtered.length) {
    el.innerHTML = '<p class="empty">尚無聊天紀錄</p>';
    return;
  }

  const groups = groupSessions(filtered);
  for (const [label, items] of Object.entries(groups)) {
    if (!items.length) continue;
    const title = document.createElement("div");
    title.className =
      "history-group-title" + (label === "已釘選" ? " history-group-pinned" : "");
    title.textContent = label;
    el.appendChild(title);

    for (const s of items) {
      appendHistoryItem(el, s);
    }
  }
}

