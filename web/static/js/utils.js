/* js/utils.js */
function hashStr(s) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function avatarGradient(slug) {
  const g = AVATAR_GRADIENTS[hashStr(slug || "") % AVATAR_GRADIENTS.length];
  return `linear-gradient(135deg, ${g[0]}, ${g[1]})`;
}

function initials(name) {
  if (!name) return "?";
  const s = String(name).trim();
  if (/[\u4e00-\u9fff]/.test(s)) return s.slice(0, 1);
  return s.slice(0, 2).toUpperCase();
}

function personAvatarUrl(slug) {
  const p = persons.find((x) => x.slug === slug);
  if (p?.avatar_url) return p.avatar_url;
  return memberAvatarFromSession(slug);
}

function memberAvatarFromSession(slug) {
  const member = (currentSession?.members || []).find(
    (m) => m.person_slug === slug
  );
  return member?.avatar_url || "";
}

function removeTypingIndicator() {
  document.getElementById("typingIndicator")?.remove();
}

function showTypingIndicator(speaker) {
  removeTypingIndicator();
  if (!speaker) return;

  const box = document.getElementById("chatMessages");
  const empty = box.querySelector(".empty");
  if (empty) empty.remove();

  const name = speaker.name_zh || "發言者";
  const slug = speaker.person_slug || "";
  const kind = speaker.kind || "celeb";
  const phase = speaker.phase || "";

  let avUrl = speaker.avatar_url || "";
  if (!avUrl && kind === "user_twin") avUrl = profile?.avatar_url || "";
  if (!avUrl && slug) avUrl = personAvatarUrl(slug);

  const row = document.createElement("div");
  row.id = "typingIndicator";
  row.className = "msg-row msg-row--assistant msg-row--typing";
  if (kind === "user_twin") row.className += " msg-row--user-twin";

  const avatarSlot = document.createElement("div");
  avatarSlot.className = "msg-avatar-slot";
  if (kind === "conclusion") {
    const av = document.createElement("div");
    av.className = "avatar conclusion-avatar";
    av.textContent = "結";
    avatarSlot.appendChild(av);
  } else if (kind === "user_twin") {
    avatarSlot.appendChild(
      avatarEl(
        profile?.display_name || "你",
        profile?.avatar_url ? "avatar user-photo" : "avatar user-avatar",
        "",
        avUrl
      )
    );
  } else {
    avatarSlot.appendChild(avatarEl(name, "avatar", slug, avUrl));
  }
  row.appendChild(avatarSlot);

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble msg-bubble--typing";

  const who = document.createElement("div");
  who.className = "msg-who";
  if (phase === "opening") who.textContent = `${name} · 開場`;
  else if (phase === "debate") who.textContent = `${name} · 回應`;
  else if (kind === "conclusion") who.textContent = "討論結論";
  else who.textContent = name;
  bubble.appendChild(who);

  const body = document.createElement("div");
  body.className = "msg-body msg-body--typing";
  const label = document.createElement("span");
  label.className = "typing-label";
  label.textContent = kind === "conclusion" ? "正在整理結論" : "正在輸入";
  body.appendChild(label);
  const dots = document.createElement("span");
  dots.className = "typing-dots";
  dots.setAttribute("aria-hidden", "true");
  dots.innerHTML = "<span></span><span></span><span></span>";
  body.appendChild(dots);
  bubble.appendChild(body);

  row.appendChild(bubble);
  box.appendChild(row);
  box.scrollTop = box.scrollHeight;
}

const SOURCE_TYPE_ZH = {
  speech: "演講",
  news: "新聞",
  web: "網頁",
  wiki: "維基百科",
  interview: "訪談",
  other: "其他",
};

function humanSourceType(type) {
  if (!type) return "公開資料";
  const key = String(type).toLowerCase();
  return SOURCE_TYPE_ZH[key] || type;
}

function refsFootnoteLabel(count) {
  if (count <= 0) return "";
  if (count === 1) return "參考了 1 份公開資料";
  return `參考了 ${count} 份公開資料`;
}

function truncateQuote(text, max = 220) {
  const t = (text || "").trim();
  if (!t) return "（這段資料暫無摘要）";
  if (t.length <= max) return t;
  return t.slice(0, max) + "…";
}

function avatarEl(name, className = "avatar", slug = "", avatarUrl = "") {
  const url = avatarUrl || (slug ? personAvatarUrl(slug) : "");
  if (url) {
    const img = document.createElement("img");
    img.className = className + " avatar-img";
    img.src = url;
    img.alt = name || "";
    img.loading = "lazy";
    img.onerror = () => {
      const fallback = document.createElement("div");
      fallback.className = className;
      fallback.textContent = initials(name);
      if (slug) fallback.style.background = avatarGradient(slug);
      img.replaceWith(fallback);
    };
    return img;
  }
  const d = document.createElement("div");
  d.className = className;
  d.textContent = initials(name);
  if (slug) d.style.background = avatarGradient(slug);
  return d;
}

function formatViews(docCount) {
  const n = Math.max(1, (docCount || 0) * 1200 + hashStr(String(docCount)) % 50000);
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "m";
  if (n >= 1000) return (n / 1000).toFixed(1) + "k";
  return String(n);
}

function loadRoomsStore() {
  const key = roomsStoreKey();
  try {
    const raw = localStorage.getItem(key);
    if (!raw) {
      return { owned: [], joined: [], migrated: false };
    }
    const data = JSON.parse(raw);
    return {
      owned: data.owned || [],
      joined: data.joined || [],
      migrated: !!data.migrated,
    };
  } catch {
    return { owned: [], joined: [], migrated: false };
  }
}

function saveRoomsStore(store) {
  localStorage.setItem(roomsStoreKey(), JSON.stringify(store));
}

function roomsStoreKey() {
  const base = DT_ROOMS_KEY || "dt_rooms";
  if (isAuthenticated && profile?.id != null) {
    return `${base}:user:${profile.id}`;
  }
  if (isAuthenticated && profile?.username) {
    return `${base}:user:${profile.username}`;
  }
  if (!isAuthenticated && profile?.display_name) {
    return `${base}:guest:${profile.display_name}`;
  }
  return `${base}:anon`;
}

function registerOwnedSession(session) {
  const store = loadRoomsStore();
  const entry = {
    id: session.id,
    join_code: session.join_code || "",
    has_password: !!session.has_password,
  };
  store.owned = store.owned.filter((o) => o.id !== session.id);
  store.owned.unshift(entry);
  saveRoomsStore(store);
}

function registerJoinedSession(session, guestName = "") {
  const store = loadRoomsStore();
  const entry = {
    id: session.id,
    join_code: session.join_code || "",
    guest_name: (guestName || "").trim(),
  };
  store.joined = store.joined.filter((j) => j.id !== session.id);
  store.joined.unshift(entry);
  saveRoomsStore(store);
}

function unregisterSession(sessionId) {
  const id = Number(sessionId);
  if (!Number.isFinite(id)) return;
  const store = loadRoomsStore();
  store.owned = (store.owned || []).filter((o) => o.id !== id);
  store.joined = (store.joined || []).filter((j) => j.id !== id);
  saveRoomsStore(store);
}

function getKnownSessionIds() {
  const store = loadRoomsStore();
  const ids = new Set();
  store.owned.forEach((o) => ids.add(o.id));
  store.joined.forEach((j) => ids.add(j.id));
  return [...ids];
}

function getAccessForSession(sessionId) {
  const store = loadRoomsStore();
  if (store.owned.some((o) => o.id === sessionId)) {
    return { isOwner: true, guestToken: null, guestName: null };
  }
  const j = store.joined.find((x) => x.id === sessionId);
  if (j) {
    return {
      isOwner: false,
      guestToken: null,
      guestName: j.guest_name || null,
    };
  }
  return { isOwner: false, guestToken: null, guestName: null };
}

function sessionAuthHeaders(sessionId) {
  const h = {};
  if (!sessionId) return h;
  const access = getAccessForSession(sessionId);
  if (access.isOwner) h["X-Session-Owner"] = "1";
  if (access.guestToken) h["X-Guest-Token"] = access.guestToken;
  return h;
}

async function migrateRoomsOnce() {
  const store = loadRoomsStore();
  if (store.migrated) return;
  // 帳號分流後不再使用舊版「全域聊天室 id 遷移」，
  // 避免不同帳號看到彼此本機歷史。
  store.migrated = true;
  saveRoomsStore(store);
}

async function fetchJson(url, opts = {}, sessionId = null) {
  const { signal, headers: extraHeaders, ...rest } = opts;
  const headers = {
    "Content-Type": "application/json",
    ...(extraHeaders || {}),
    ...sessionAuthHeaders(sessionId),
  };
  const res = await fetch(API + url, {
    ...rest,
    signal,
    headers,
    credentials: "include",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const msg = Array.isArray(detail)
      ? detail.map((d) => d.msg || d).join(", ")
      : detail || res.statusText || "請求失敗";
    throw new Error(msg);
  }
  return data;
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s ?? "";
  return d.innerHTML;
}

function accountDisplayName() {
  return (
    profile?.display_name ||
    profile?.username ||
    profile?.account_name ||
    "你"
  );
}

function speakerName(m) {
  if (m.role === "user") {
    if (m.is_guest && m.person_name_zh) return m.person_name_zh;
    return accountDisplayName();
  }
  if (m.role === "user_twin") {
    return m.person_name_zh || `${profile?.display_name || "你"}（分身）`;
  }
  if (m.role === "conclusion") return "討論結論";
  return m.person_name_zh || m.role || "分身";
}

function isUserMessage(m) {
  return m.role === "user";
}

function isGuestMessage(m) {
  return m.role === "user" && m.is_guest;
}

function isUserTwinMessage(m) {
  return m.role === "user_twin";
}

function isConclusionMessage(m) {
  return m.role === "conclusion";
}

function filterPersons(query) {
  const q = query.trim().toLowerCase();
  if (!q) return persons;
  return persons.filter((p) => {
    const hay = [p.name_zh, p.name_en, p.slug, p.bio]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return hay.includes(q);
  });
}

