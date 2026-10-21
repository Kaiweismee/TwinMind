/* js/session.js */
function showDiscover() {
  stopAutoDiscussion();
  hideAllMainViews();
  document.getElementById("discoverView")?.classList.remove("hidden");
  document.getElementById("roomAccessRow")?.classList.add("hidden");
  currentSessionId = null;
  loadNotifications();
  if (typeof setDiscoverMediaRailVisible === "function") {
    setDiscoverMediaRailVisible(false);
  }
  document.querySelectorAll(".nav-item").forEach((n) => {
    n.classList.toggle("active", n.dataset.nav === "discover");
  });
  renderHistory(document.getElementById("historySearch").value);
}

function showMediaLibraryHome() {
  showDiscover();
  if (typeof setDiscoverMediaRailVisible === "function") {
    setDiscoverMediaRailVisible(true);
  }
  document.querySelectorAll(".nav-item").forEach((n) => {
    n.classList.toggle("active", n.dataset.nav === "labs");
  });
}

function showChat() {
  hideAllMainViews();
  document.getElementById("chatView")?.classList.add("visible");
}

async function openSession(id) {
  stopAutoDiscussion();
  await waitTurnIdle();

  let data;
  try {
    data = await fetchJson(`/api/sessions/${id}`, {}, id);
  } catch (e) {
    if (String(e.message).includes("密碼")) {
      openJoinModal();
    }
    throw e;
  }
  currentSessionId = id;
  currentSession = data.session;
  showChat();
  clearSourcesDrawer();

  const members = currentSession.members || [];
  const title = sessionTopic(currentSession);

  document.getElementById("chatTitle").textContent = title;
  setDiscussSubtitle(defaultDiscussSubtitle());

  const av = document.getElementById("chatAvatar");
  av.textContent = members.length > 1 ? "多" : initials(members[0]?.name_zh || title);
  if (members[0]) av.style.background = avatarGradient(members[0].person_slug);

  renderParticipantChips(currentSession);
  refreshChatReplyPicker();
  renderMessages(data.messages || []);
  scheduleInsightsRefresh(false);
  maybeAutoOpenInsights(data.messages || []);
  renderHistory(document.getElementById("historySearch").value);

  try {
    const state = await fetchJson(
      `/api/sessions/${currentSessionId}/turn-state`,
      {},
      currentSessionId
    );
    updateRoomBanner(data.session);
    const access = getAccessForSession(id);
    if (state.done) {
      setDiscussSubtitle("討論已結束");
      maybeAutoOpenInsights(data.messages || [], true);
    } else if (access.isOwner) {
      runAutoDiscussion();
    } else {
      setDiscussSubtitle("已加入討論室 · 可插話參與，名人討論由房主啟動");
    }
  } catch {
    const access = getAccessForSession(id);
    if (access.isOwner) runAutoDiscussion();
  }
}

let turnInFlight = false;
let autoDiscussAbort = false;
const TURN_GAP_MS = 750;

function resetTurnLock() {
  autoDiscussAbort = true;
  turnInFlight = false;
}

async function refreshTurnUi() {
  if (!currentSessionId) return;
  try {
    const state = await fetchJson(
      `/api/sessions/${currentSessionId}/turn-state`,
      {},
      currentSessionId
    );
    if (state.done) {
      setDiscussSubtitle("討論已結束");
      maybeAutoOpenInsights(null, true);
      scheduleInsightsRefresh(true);
    } else if (!autoDiscussAbort) {
      const who = state.next_label || "下一輪";
      setDiscussSubtitle(`自動討論中 · ${who}`);
    }
  } catch {
    /* ignore */
  }
}

/** 執行單一 turn；回傳 done | ok | error */
async function requestNextTurn() {
  if (!currentSessionId || turnInFlight || window.__directReplyInFlight) return "busy";
  turnInFlight = true;

  try {
    const state = await fetchJson(
      `/api/sessions/${currentSessionId}/turn-state`,
      {},
      currentSessionId
    );
    if (autoDiscussAbort || window.__directReplyInFlight) return "busy";
    if (state.done) return "done";

    showTypingIndicator(state.next_speaker);
    if (state.next_label) setDiscussSubtitle(`自動討論中 · ${state.next_label}`);
    if (typeof refreshInsightsWhileThinking === "function") {
      refreshInsightsWhileThinking(visibleChatMessageCount()).catch(() => {});
    }

    const data = await fetchJson(
      `/api/sessions/${currentSessionId}/turn`,
      { method: "POST", body: JSON.stringify({}) },
      currentSessionId
    );
    removeTypingIndicator();
    if (data.message) appendMessageBubble(data.message);
    await loadSessions();
    if (data.done) {
      setDiscussSubtitle("討論已結束");
      maybeAutoOpenInsights(null, true);
      scheduleInsightsRefresh(true);
      return "done";
    }
    await refreshTurnUi();
    return "ok";
  } catch (err) {
    removeTypingIndicator();
    alert(err.message);
    return "error";
  } finally {
    turnInFlight = false;
  }
}

async function runAutoDiscussion() {
  if (!currentSessionId) return;
  autoDiscussAbort = false;
  setDiscussSubtitle("自動討論中，你也可以隨時插話…");
  if (typeof ensureInsightsPanelForLive === "function") ensureInsightsPanelForLive();

  while (!autoDiscussAbort && currentSessionId) {
    if (window.__directReplyInFlight) break;
    const state = await fetchJson(
      `/api/sessions/${currentSessionId}/turn-state`,
      {},
      currentSessionId
    );
    if (autoDiscussAbort || window.__directReplyInFlight) break;
    if (state.done) {
      setDiscussSubtitle("討論已結束");
      maybeAutoOpenInsights(null, true);
      scheduleInsightsRefresh(true);
      break;
    }

    const result = await requestNextTurn();
    if (result === "done" || result === "error" || autoDiscussAbort) break;
    if (result === "busy") break;

    await sleep(TURN_GAP_MS);
  }
}

function updateRoomBanner(session) {
  const row = document.getElementById("roomAccessRow");
  if (!row) return;
  row.innerHTML = "";
  if (!session?.join_code) {
    row.classList.add("hidden");
    return;
  }
  const access = getAccessForSession(session.id);
  const code = session.join_code;

  row.classList.remove("hidden");

  if (access.isOwner) {
    const codeChip = document.createElement("button");
    codeChip.type = "button";
    codeChip.className = "chip chip-join chip-join--copy";
    codeChip.title = "點擊複製加入碼";
    codeChip.textContent = `加入碼 ${code}`;
    codeChip.addEventListener("click", (e) => {
      e.stopPropagation();
      const copy = () => {
        codeChip.textContent = "已複製";
        codeChip.classList.add("chip-join--copied");
        setTimeout(() => {
          codeChip.textContent = `加入碼 ${code}`;
          codeChip.classList.remove("chip-join--copied");
        }, 1500);
      };
      if (navigator.clipboard?.writeText) {
        navigator.clipboard.writeText(code).then(copy).catch(() => {});
      }
    });
    row.appendChild(codeChip);

    if (session.has_password) {
      const lockChip = document.createElement("span");
      lockChip.className = "chip chip-lock";
      lockChip.textContent = "已設密碼";
      row.appendChild(lockChip);
    }
  } else if (access.guestName) {
    const guestChip = document.createElement("span");
    guestChip.className = "chip chip-guest";
    guestChip.textContent = `${access.guestName} · 已加入`;
    row.appendChild(guestChip);

    const codeChip = document.createElement("span");
    codeChip.className = "chip chip-join";
    codeChip.textContent = code;
    row.appendChild(codeChip);
  } else {
    row.classList.add("hidden");
  }
}

async function uploadSessionContext(sessionId, files) {
  if (!files?.length) return null;
  const fd = new FormData();
  for (const file of files) fd.append("files", file);
  const headers = {
    ...sessionAuthHeaders(sessionId),
  };
  const res = await fetch(API + `/api/sessions/${sessionId}/context`, {
    method: "POST",
    body: fd,
    headers,
    credentials: "include",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const msg = Array.isArray(detail)
      ? detail.map((d) => d.msg || d).join(", ")
      : detail || res.statusText || "參考檔上傳失敗";
    throw new Error(msg);
  }
  return data;
}

async function createRoom(slugs, title, opts = {}) {
  const {
    roomPassword = "",
    allowGuestJoin = true,
    contextFiles = createRoomPendingFiles,
  } = typeof opts === "string" ? { roomPassword: opts } : opts;

  stopAutoDiscussion();
  resetTurnLock();

  const data = await fetchJson("/api/sessions", {
    method: "POST",
    body: JSON.stringify({
      person_slugs: slugs,
      title: title || "",
      room_password: allowGuestJoin ? roomPassword || "" : "",
      allow_guest_join: allowGuestJoin,
    }),
  });
  const pending = contextFiles?.length ? [...contextFiles] : [];
  if (pending.length) {
    await uploadSessionContext(data.session.id, pending);
    createRoomPendingFiles = [];
    if (typeof renderCreateRoomAttachPreview === "function") {
      renderCreateRoomAttachPreview();
    }
  }
  registerOwnedSession(data.session);
  await loadSessions();
  loadNotifications();
  await openSession(data.session.id);
  const code = data.session.join_code;
  if (!allowGuestJoin) {
    alert("討論室已建立！\n\n此房間未開放他人加入。");
    return;
  }
  const pwdMsg = roomPassword ? "\n密碼已設定，請分享加入碼與密碼給朋友。" : "";
  if (code) alert(`討論室已建立！\n\n加入碼：${code}${pwdMsg}`);
}

async function loadPersonChatThreads() {
  if (!isAuthenticated) {
    personChatThreads = [];
    return;
  }
  try {
    const data = await fetchJson("/api/person-chat/threads");
    personChatThreads = data.threads || [];
  } catch (err) {
    console.error(err);
    personChatThreads = [];
  }
}

async function loadSessions() {
  await migrateRoomsOnce();
  const ids = getKnownSessionIds();
  const [ownedData, knownData] = await Promise.all([
    fetchJson("/api/sessions"),
    ids.length > 0 ? fetchJson(`/api/sessions?ids=${ids.join(",")}`) : Promise.resolve({ sessions: [] }),
  ]);
  await loadPersonChatThreads();
  const ownedIds = new Set((ownedData.sessions || []).map((s) => s.id));
  const knownSessions = (knownData.sessions || []).filter((s) => {
    // 清理舊資料污染：本機標記為房主、但伺服器判定不是目前帳號房主時，移除本機記錄。
    if (isAuthenticated) {
      const access = getAccessForSession(s.id);
      if (access.isOwner && !ownedIds.has(s.id)) {
        unregisterSession(s.id);
        return false;
      }
    }
    return true;
  });
  const byId = new Map();
  for (const s of ownedData.sessions || []) byId.set(s.id, s);
  for (const s of knownSessions) byId.set(s.id, s);
  sessions = [...byId.values()].sort((a, b) => {
    const ta = Date.parse(a.updated_at || a.created_at || 0);
    const tb = Date.parse(b.updated_at || b.created_at || 0);
    return tb - ta;
  });
  renderHistory(document.getElementById("historySearch").value);
}

async function joinRoom() {
  if (!isAuthenticated) {
    alert("請先登入後再加入討論室");
    showAuthGate();
    return;
  }
  const code = (document.getElementById("joinCode")?.value || "").trim();
  const pwd = (document.getElementById("joinPassword")?.value || "").trim();
  const ownName =
    (profile?.display_name || profile?.username || profile?.name || "").trim();
  const nameInput = document.getElementById("joinGuestName");
  const name = (nameInput?.value || ownName || "").trim();
  if (!code) {
    alert("請輸入加入碼");
    return;
  }
  if (!name) {
    alert("請輸入你的暱稱");
    return;
  }
  try {
    const data = await fetchJson("/api/sessions/join", {
      method: "POST",
      body: JSON.stringify({
        join_code: code,
        password: pwd,
        guest_name: name,
      }),
    });
    registerJoinedSession(data.session, data.guest_name || name);
    closeJoinModal();
    await loadSessions();
    await openSession(data.session.id);
  } catch (e) {
    alert(e.message);
  }
}

function openJoinModal() {
  if (!isAuthenticated) {
    alert("請先登入後再加入討論室");
    showAuthGate();
    return;
  }
  const ownName =
    (profile?.display_name || profile?.username || profile?.name || "").trim();
  const joinNameInput = document.getElementById("joinGuestName");
  if (joinNameInput && !joinNameInput.value.trim()) {
    joinNameInput.value = ownName;
  }
  document.getElementById("joinModal")?.classList.add("open");
  document.getElementById("joinCode")?.focus();
}

function closeJoinModal() {
  document.getElementById("joinModal")?.classList.remove("open");
}

async function previewJoinCode() {
  const code = (document.getElementById("joinCode")?.value || "").trim();
  const hint = document.getElementById("joinPreview");
  if (!hint) return;
  if (!code) {
    hint.textContent = "";
    return;
  }
  try {
    const p = await fetchJson(`/api/sessions/preview/${encodeURIComponent(code)}`);
    hint.textContent = `${p.topic} · ${p.members_label || ""}${
      p.has_password ? " · 需密碼" : ""
    }`;
  } catch {
    hint.textContent = "找不到此加入碼";
  }
}
