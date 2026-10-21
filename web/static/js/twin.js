/* js/twin.js */
function hideAllMainViews() {
  document.getElementById("discoverView")?.classList.add("hidden");
  document.getElementById("chatView")?.classList.remove("visible");
  const twinView = document.getElementById("twinChatView");
  twinView?.classList.remove("visible");
  twinView?.classList.add("hidden");
  twinChatVisible = false;
}

function twinChatEmptyText() {
  if (twinChatMode === "person" && twinChatPerson) {
    const name = twinChatPerson.name_zh || "名人";
    return `開始和${name}聊聊吧，想問什麼都可以。`;
  }
  return "開始和分身聊聊吧，也可以上傳圖片、PDF 或 Word（.docx）檔案。";
}

function twinAssistantAvatarNode() {
  if (twinChatMode === "person" && twinChatPerson) {
    return avatarEl(
      twinChatPerson.name_zh,
      "avatar sm",
      twinChatPerson.slug,
      twinChatPerson.avatar_url
    );
  }
  return avatarEl(
    profile?.twin_name || "分身",
    profile?.avatar_url ? "avatar sm user-photo" : "avatar sm user-avatar",
    "",
    profile?.avatar_url || ""
  );
}

function shouldShowAssistantAvatar() {
  return twinChatMode === "person" && !!twinChatPerson;
}

function updateTwinChatHeader() {
  const host = document.getElementById("twinChatAvatarHost");
  const title = document.getElementById("twinChatTitle");
  const subtitle = document.getElementById("twinChatSubtitle");
  if (!host || !title || !subtitle) return;

  host.innerHTML = "";
  if (twinChatMode === "person" && twinChatPerson) {
    title.textContent = twinChatPerson.name_zh || "名人";
    subtitle.textContent = twinChatPerson.bio || "與他一對一聊聊";
    host.appendChild(
      avatarEl(
        twinChatPerson.name_zh,
        "avatar sm",
        twinChatPerson.slug,
        twinChatPerson.avatar_url
      )
    );
    return;
  }

  const twinName = profile?.twin_name || "數位分身";
  const preset = (profile?.twins || []).find((t) => t.is_active)?.preset || "life";
  title.textContent = `${twinName}分身`;
  subtitle.textContent = TWIN_PRESET_HINTS[preset] || TWIN_PRESET_HINTS.life;
  host.appendChild(
    avatarEl(
      twinName,
      profile?.avatar_url ? "avatar sm user-photo" : "avatar sm user-avatar",
      "",
      profile?.avatar_url || ""
    )
  );
}

function refreshSidebarHistory() {
  if (typeof loadPersonChatThreads === "function") {
    loadPersonChatThreads().then(() => {
      renderHistory(document.getElementById("historySearch")?.value || "");
    });
    return;
  }
  renderHistory(document.getElementById("historySearch")?.value || "");
}

function renderTwinAttachPreview() {
  const box = document.getElementById("twinAttachPreview");
  if (!box) return;
  box.innerHTML = "";
  if (!twinPendingFiles.length) {
    box.classList.add("hidden");
    return;
  }
  box.classList.remove("hidden");
  twinPendingFiles.forEach((file, idx) => {
    const chip = document.createElement("span");
    chip.className = "twin-attach-chip";
    chip.innerHTML = `<span>${escapeHtml(file.name)}</span>`;
    const rm = document.createElement("button");
    rm.type = "button";
    rm.textContent = "×";
    rm.addEventListener("click", () => {
      twinPendingFiles.splice(idx, 1);
      renderTwinAttachPreview();
    });
    chip.appendChild(rm);
    box.appendChild(chip);
  });
}

function upsertTwinTypingIndicator(role, visible) {
  const box = document.getElementById("twinChatMessages");
  if (!box) return;
  const cls = role === "user" ? "twin-msg--user" : "twin-msg--assistant";
  const rowId = `twinTypingRow-${role}`;
  const existing = document.getElementById(rowId);
  if (!visible) {
    existing?.remove();
    return;
  }
  if (existing) return;

  box.querySelector(".twin-chat-empty")?.remove();
  const row = document.createElement("div");
  row.id = rowId;
  row.className = `twin-msg ${cls} twin-msg--typing`;

  if (role === "user" || (role === "assistant" && shouldShowAssistantAvatar())) {
    const avatarWrap = document.createElement("div");
    avatarWrap.className = "twin-msg-avatar";
    const avatarNode =
      role === "user"
        ? avatarEl(
            profile?.account_name || profile?.display_name || profile?.username || "你",
            profile?.avatar_url ? "avatar sm user-photo" : "avatar sm",
            "",
            profile?.avatar_url || ""
          )
        : twinAssistantAvatarNode();
    avatarWrap.appendChild(avatarNode);
    row.appendChild(avatarWrap);
  }

  const bubble = document.createElement("div");
  bubble.className = "twin-msg-bubble twin-msg-bubble--typing";
  bubble.textContent = "...";
  row.appendChild(bubble);
  box.appendChild(row);
  box.scrollTop = box.scrollHeight;
}

function clearTwinTypingIndicators() {
  upsertTwinTypingIndicator("user", false);
  upsertTwinTypingIndicator("assistant", false);
}

function appendTwinBubble(msg) {
  const box = document.getElementById("twinChatMessages");
  if (!box) return;
  box.querySelector(".twin-chat-empty")?.remove();
  if (msg.role === "user") {
    upsertTwinTypingIndicator("user", false);
  } else {
    upsertTwinTypingIndicator("assistant", false);
  }

  const isUser = msg.role === "user";
  const row = document.createElement("div");
  row.className = "twin-msg " + (isUser ? "twin-msg--user" : "twin-msg--assistant");

  const userName =
    profile?.account_name || profile?.display_name || profile?.username || "你";

  const bubble = document.createElement("div");
  bubble.className = "twin-msg-bubble";
  bubble.textContent = msg.content || "";

  const attachments = msg.attachments || [];
  if (attachments.length) {
    const attWrap = document.createElement("div");
    attWrap.className = "twin-msg-attachments";
    for (const a of attachments) {
      if (a.kind === "image" && a.url) {
        const img = document.createElement("img");
        img.src = a.url;
        img.alt = a.name || "圖片";
        attWrap.appendChild(img);
      } else {
        const fileName = (a.name || "檔案").trim();
        const ext = (fileName.split(".").pop() || "").toLowerCase();
        const hasUrl = !!a.url;
        const tag = hasUrl ? document.createElement("a") : document.createElement("span");
        tag.className = `twin-msg-file${ext ? ` twin-msg-file--${ext}` : ""}`;
        if (hasUrl && tag instanceof HTMLAnchorElement) {
          tag.href = a.url;
          tag.target = "_blank";
          tag.rel = "noopener noreferrer";
        }
        tag.innerHTML = `
          <span class="twin-msg-file-icon" aria-hidden="true">📄</span>
          <span class="twin-msg-file-name">${escapeHtml(fileName)}</span>
        `;
        attWrap.appendChild(tag);
      }
    }
    bubble.appendChild(attWrap);
  }

  if (isUser) {
    const avatarWrap = document.createElement("div");
    avatarWrap.className = "twin-msg-avatar";
    const avatarNode = avatarEl(
      userName,
      profile?.avatar_url ? "avatar sm user-photo" : "avatar sm",
      "",
      profile?.avatar_url || ""
    );
    avatarWrap.appendChild(avatarNode);
    row.appendChild(avatarWrap);
  } else if (shouldShowAssistantAvatar()) {
    const avatarWrap = document.createElement("div");
    avatarWrap.className = "twin-msg-avatar";
    avatarWrap.appendChild(twinAssistantAvatarNode());
    row.appendChild(avatarWrap);
  }

  row.appendChild(bubble);
  box.appendChild(row);
  box.scrollTop = box.scrollHeight;
  return row;
}

function renderTwinMessages(messages) {
  const box = document.getElementById("twinChatMessages");
  if (!box) return;
  box.innerHTML = "";
  if (!messages.length) {
    box.innerHTML = `<p class="twin-chat-empty">${escapeHtml(twinChatEmptyText())}</p>`;
    return;
  }
  for (const m of messages) appendTwinBubble(m);
}

async function loadTwinChat() {
  if (!isAuthenticated) return;
  try {
    if (twinChatMode === "person" && twinChatPerson?.slug) {
      const data = await fetchJson(
        `/api/person-chat/messages?person_slug=${encodeURIComponent(twinChatPerson.slug)}`
      );
      if (data.person) twinChatPerson = { ...twinChatPerson, ...data.person };
      updateTwinChatHeader();
      renderTwinMessages(data.messages || []);
      return;
    }
    if (!profile?.active_twin_id) return;
    const data = await fetchJson("/api/twin-chat/messages");
    renderTwinMessages(data.messages || []);
  } catch (err) {
    console.error(err);
  }
}

async function sendTwinMessage(e) {
  e?.preventDefault();
  if (twinChatSending || !isAuthenticated) return;
  const input = document.getElementById("twinChatInput");
  const text = (input?.value || "").trim();
  const isPerson = twinChatMode === "person" && twinChatPerson?.slug;
  if (!text && !twinPendingFiles.length) return;
  const pendingFiles = [...twinPendingFiles];
  let optimisticUserRow = null;

  twinChatSending = true;
  const form = document.getElementById("twinChatForm");
  const sendBtn = document.getElementById("btnTwinSend");
  form?.classList.add("twin-composer--thinking");
  if (sendBtn) sendBtn.disabled = true;

  optimisticUserRow = appendTwinBubble({
    role: "user",
    content: text,
    attachments: pendingFiles.map((f) => ({ kind: "file", name: f.name })),
  });

  if (input) input.value = "";
  twinPendingFiles = [];
  renderTwinAttachPreview();
  upsertTwinTypingIndicator("user", false);
  upsertTwinTypingIndicator("assistant", true);

  try {
    let res;
    if (isPerson) {
      const fd = new FormData();
      fd.append("person_slug", twinChatPerson.slug);
      fd.append("content", text);
      for (const file of pendingFiles) fd.append("files", file);
      res = await fetch(API + "/api/person-chat/messages", {
        method: "POST",
        body: fd,
        credentials: "include",
      });
    } else {
      const fd = new FormData();
      fd.append("content", text);
      for (const file of pendingFiles) fd.append("files", file);
      res = await fetch(API + "/api/twin-chat/messages", {
        method: "POST",
        body: fd,
        credentials: "include",
      });
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data.detail;
      throw new Error(
        typeof detail === "string" ? detail : detail?.[0]?.msg || "傳送失敗"
      );
    }
    if (data.assistant_message) appendTwinBubble(data.assistant_message);
    if (isPerson) refreshSidebarHistory();
  } catch (err) {
    optimisticUserRow?.remove();
    alert(err.message);
  } finally {
    twinChatSending = false;
    form?.classList.remove("twin-composer--thinking");
    if (sendBtn) sendBtn.disabled = false;
    clearTwinTypingIndicators();
  }
}

function openTwinChatView() {
  stopAutoDiscussion();
  hideAllMainViews();
  const twinView = document.getElementById("twinChatView");
  twinView?.classList.remove("hidden");
  twinView?.classList.add("visible");
  twinChatVisible = true;
  currentSessionId = null;
  updateTwinChatHeader();
  clearTwinTypingIndicators();
}

function showTwinChat() {
  if (!isAuthenticated) {
    showAuthGate();
    return;
  }
  twinChatMode = "twin";
  twinChatPerson = null;
  openTwinChatView();
  if (profile?.active_twin_id) {
    loadTwinChat();
  } else {
    renderTwinMessages([]);
  }
  document.querySelectorAll(".nav-item").forEach((n) => {
    n.classList.toggle("active", n.dataset.nav === "twin-chat");
  });
}

function showPersonChat(person) {
  if (!isAuthenticated) {
    showAuthGate();
    return;
  }
  if (!person?.slug) return;
  twinChatMode = "person";
  twinChatPerson = { ...person };
  openTwinChatView();
  loadTwinChat();
  refreshSidebarHistory();
  document.querySelectorAll(".nav-item").forEach((n) => n.classList.remove("active"));
}
