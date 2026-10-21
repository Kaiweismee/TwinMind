/* js/notify.js */
let notifyPollTimer = null;
let notifyKnownIds = new Set();
let notifyInitialized = false;

function ownedSessionIds() {
  return loadRoomsStore().owned.map((o) => o.id);
}

function formatNotifyTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const now = new Date();
  const diff = (now - d) / 1000;
  if (diff < 60) return "剛才";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分鐘前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小時前`;
  return d.toLocaleString("zh-TW", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderNotifyList(items) {
  const list = document.getElementById("notifyList");
  if (!list) return;
  if (!items.length) {
    list.innerHTML = '<p class="notify-empty">尚無加入通知</p>';
    return;
  }
  list.innerHTML = "";
  for (const n of items) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "notify-item";
    btn.dataset.sessionId = String(n.session_id);
    const topic = (n.session_topic || "").trim() || "討論室";
    btn.innerHTML = `
      <strong>${escapeHtml(n.guest_name)} 加入了討論</strong>
      <span>${escapeHtml(topic)}</span>
      <time>${escapeHtml(formatNotifyTime(n.created_at))}</time>`;
    btn.addEventListener("click", async () => {
      closeNotifyDropdown();
      await markNotificationsRead();
      await openSession(n.session_id);
    });
    list.appendChild(btn);
  }
}

function updateNotifyBadge(count) {
  const badge = document.getElementById("notifyBadge");
  if (!badge) return;
  if (count > 0) badge.classList.remove("hidden");
  else badge.classList.add("hidden");
}

function ensureNotifyToastHost() {
  let host = document.getElementById("notifyToastHost");
  if (host) return host;
  host = document.createElement("div");
  host.id = "notifyToastHost";
  host.className = "notify-toast-host";
  document.body.appendChild(host);
  return host;
}

function pushJoinToast(item) {
  if (!item?.guest_name) return;
  const host = ensureNotifyToastHost();
  const el = document.createElement("div");
  el.className = "notify-toast";
  const topic = (item.session_topic || "").trim() || "討論室";
  el.innerHTML = `
    <strong>${escapeHtml(item.guest_name)} 已加入會議</strong>
    <span>${escapeHtml(topic)}</span>
  `;
  host.appendChild(el);
  window.setTimeout(() => el.classList.add("show"), 10);
  window.setTimeout(() => {
    el.classList.remove("show");
    window.setTimeout(() => el.remove(), 220);
  }, 3200);
}

async function loadNotifications({ unreadOnly = true, showToasts = true } = {}) {
  const ids = ownedSessionIds();
  try {
    const query = isAuthenticated
      ? `unread_only=${unreadOnly}`
      : (ids.length
          ? `ids=${ids.join(",")}&unread_only=${unreadOnly}`
          : `unread_only=${unreadOnly}`);
    const data = await fetchJson(`/api/notifications?${query}`);
    const items = data.notifications || [];
    if (showToasts && unreadOnly) {
      if (notifyInitialized) {
        for (const n of items) {
          if (n?.id != null && !notifyKnownIds.has(n.id)) pushJoinToast(n);
        }
      }
      for (const n of items) {
        if (n?.id != null) notifyKnownIds.add(n.id);
      }
      notifyInitialized = true;
    }
    updateNotifyBadge(data.unread_count || 0);
    renderNotifyList(items);
  } catch {
    updateNotifyBadge(0);
    renderNotifyList([]);
  }
}

async function markNotificationsRead({ refreshList = false } = {}) {
  const ids = ownedSessionIds();
  try {
    const body = isAuthenticated
      ? {}
      : (ids.length ? { session_ids: ids } : {});
    await fetchJson("/api/notifications/read", {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (refreshList) {
      await loadNotifications({ unreadOnly: false, showToasts: false });
    } else {
      updateNotifyBadge(0);
    }
  } catch {
    /* ignore */
  }
}

function closeNotifyDropdown() {
  const dd = document.getElementById("notifyDropdown");
  const btn = document.getElementById("btnNotify");
  dd?.classList.add("hidden");
  btn?.setAttribute("aria-expanded", "false");
}

async function toggleNotifyDropdown() {
  const dd = document.getElementById("notifyDropdown");
  const btn = document.getElementById("btnNotify");
  if (!dd || !btn) return;
  const open = dd.classList.contains("hidden");
  if (open) {
    await loadNotifications({ unreadOnly: false, showToasts: false });
    dd.classList.remove("hidden");
    btn.setAttribute("aria-expanded", "true");
    await markNotificationsRead({ refreshList: true });
  } else {
    closeNotifyDropdown();
  }
}

function startNotifyPolling() {
  if (notifyPollTimer) clearInterval(notifyPollTimer);
  notifyKnownIds = new Set();
  notifyInitialized = false;
  loadNotifications({ unreadOnly: true, showToasts: false });
  notifyPollTimer = setInterval(() => {
    loadNotifications({ unreadOnly: true, showToasts: true });
  }, 15000);
}
