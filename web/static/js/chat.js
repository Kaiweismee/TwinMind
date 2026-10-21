/* js/chat.js */
let chatReplyTarget = "all";

const CHAT_REPLY_TARGETS = {
  all: { id: "all", label: "所有人", hint: "公開插話" },
  user_twin: { id: "user_twin", label: "你的分身", hint: "分身" },
};

function chatReplyAllIconEl() {
  const el = document.createElement("span");
  el.className = "chat-reply-all-icon";
  el.textContent = "全";
  el.setAttribute("aria-hidden", "true");
  return el;
}

function chatReplyTargetMeta(targetId) {
  if (targetId === "all") return { ...CHAT_REPLY_TARGETS.all };
  if (targetId === "user_twin") {
    const name = accountDisplayName();
    return {
      id: "user_twin",
      label: `${name}（分身）`,
      hint: "分身",
      avatarUrl: profile?.avatar_url || "",
      slug: "",
    };
  }
  const members = currentSession?.members || [];
  const m = members.find((x) => (x.person_slug || x.slug) === targetId);
  if (m) {
    return {
      id: targetId,
      label: m.name_zh || targetId,
      hint: "名人",
      avatarUrl: m.avatar_url || personAvatarUrl(m.person_slug || m.slug),
      slug: m.person_slug || m.slug,
    };
  }
  return { ...CHAT_REPLY_TARGETS.all };
}

function renderChatReplyTriggerAvatar(targetId) {
  const host = document.getElementById("chatReplyTriggerAvatar");
  if (!host) return;
  host.innerHTML = "";
  if (targetId === "all") {
    host.appendChild(chatReplyAllIconEl());
    return;
  }
  const meta = chatReplyTargetMeta(targetId);
  if (targetId === "user_twin") {
    host.appendChild(
      avatarEl(
        meta.label,
        profile?.avatar_url ? "avatar sm user-photo" : "avatar sm user-avatar",
        "",
        meta.avatarUrl
      )
    );
    return;
  }
  host.appendChild(avatarEl(meta.label, "avatar sm", meta.slug, meta.avatarUrl));
}

function syncChatReplyTriggerUi() {
  const meta = chatReplyTargetMeta(chatReplyTarget);
  const label = document.getElementById("chatReplyTriggerLabel");
  if (label) label.textContent = meta.label.length > 8 ? `${meta.label.slice(0, 7)}…` : meta.label;
  renderChatReplyTriggerAvatar(chatReplyTarget);
}

function setChatReplyTarget(targetId) {
  chatReplyTarget = targetId || "all";
  syncChatReplyTriggerUi();
  document.querySelectorAll(".chat-reply-option").forEach((btn) => {
    const on = btn.dataset.target === chatReplyTarget;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
}

function closeChatReplyMenu() {
  const menu = document.getElementById("chatReplyMenu");
  const trigger = document.getElementById("chatReplyTrigger");
  menu?.classList.add("hidden");
  trigger?.setAttribute("aria-expanded", "false");
}

function openChatReplyMenu() {
  const menu = document.getElementById("chatReplyMenu");
  const trigger = document.getElementById("chatReplyTrigger");
  menu?.classList.remove("hidden");
  trigger?.setAttribute("aria-expanded", "true");
}

function toggleChatReplyMenu() {
  const menu = document.getElementById("chatReplyMenu");
  if (!menu) return;
  if (menu.classList.contains("hidden")) openChatReplyMenu();
  else closeChatReplyMenu();
}

function buildChatReplyOption(targetId, label, avatarNode) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "chat-reply-option";
  btn.dataset.target = targetId;
  btn.setAttribute("role", "option");
  const avWrap = document.createElement("span");
  avWrap.className = "chat-reply-option-avatar";
  avWrap.appendChild(avatarNode);
  const name = document.createElement("span");
  name.className = "chat-reply-option-name";
  name.textContent = label;
  btn.appendChild(avWrap);
  btn.appendChild(name);
  btn.addEventListener("click", () => {
    setChatReplyTarget(targetId);
    closeChatReplyMenu();
    document.getElementById("chatInput")?.focus();
  });
  return btn;
}

function refreshChatReplyPicker() {
  const list = document.getElementById("chatReplyMenuList");
  if (!list) return;
  list.innerHTML = "";

  list.appendChild(
    buildChatReplyOption("all", CHAT_REPLY_TARGETS.all.label, chatReplyAllIconEl())
  );

  const twinName = `${accountDisplayName()}（分身）`;
  const twinAv = avatarEl(
    twinName,
    profile?.avatar_url ? "avatar sm user-photo" : "avatar sm user-avatar",
    "",
    profile?.avatar_url || ""
  );
  list.appendChild(buildChatReplyOption("user_twin", twinName, twinAv));

  for (const m of currentSession?.members || []) {
    const slug = m.person_slug || m.slug || "";
    if (!slug) continue;
    const name = m.name_zh || slug;
    const av = avatarEl(name, "avatar sm", slug, m.avatar_url || personAvatarUrl(slug));
    list.appendChild(buildChatReplyOption(slug, name, av));
  }

  if (!CHAT_REPLY_TARGETS[chatReplyTarget] && !(currentSession?.members || []).some(
    (m) => (m.person_slug || m.slug) === chatReplyTarget
  )) {
    chatReplyTarget = "all";
  }
  setChatReplyTarget(chatReplyTarget);
  updateChatInputPlaceholder();
}

function updateChatInputPlaceholder() {
  const input = document.getElementById("chatInput");
  if (!input) return;
  const target = getChatReplyTarget();
  if (target === "all") {
    input.placeholder = "插話給所有人，將觸發一輪討論…";
  } else {
    input.placeholder = `對 ${chatReplyTargetLabel(target)} 說一句話…`;
  }
}

function initChatReplyPicker() {
  const trigger = document.getElementById("chatReplyTrigger");
  if (!trigger || trigger.dataset.bound === "1") return;
  trigger.dataset.bound = "1";
  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleChatReplyMenu();
  });
  document.addEventListener("click", (e) => {
    const picker = document.getElementById("chatReplyPicker");
    if (!picker || picker.contains(e.target)) return;
    closeChatReplyMenu();
  });
  refreshChatReplyPicker();
}

function getChatReplyTarget() {
  return chatReplyTarget || "all";
}

function chatReplyTargetLabel(targetId) {
  return chatReplyTargetMeta(targetId).label;
}

function normalizeSources(raw) {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw;
  if (typeof raw === "object" && raw.sources) return raw.sources;
  if (typeof raw === "string") {
    try {
      const p = JSON.parse(raw);
      if (Array.isArray(p)) return p;
      if (p && p.sources) return p.sources;
      return [];
    } catch {
      return [];
    }
  }
  return [];
}

function messagePayload(m) {
  let segments = m.content_segments || [];
  const sources = normalizeSources(m.sources);
  if (!segments.length && sources.length && m.content) {
    segments = parseCiteSegmentsFromContent(m.content, sources.length);
  }
  return { sources, segments };
}

/** 舊訊息若仍含 【1】／[1]，在前端還原可點擊引用 */
function parseCiteSegmentsFromContent(content, sourceCount) {
  const text = String(content || "")
    .replace(/【(\d+)】/g, "[$1]")
    .replace(/【推論】/g, "[推論]");
  const re = /([^[\]]+?)(?:\[(\d+)\]|\[推論\])/g;
  const segments = [];
  let last = 0;
  let m;
  while ((m = re.exec(text)) !== null) {
    const clause = (m[1] || "").trim();
    if (!clause) {
      last = m.index + m[0].length;
      continue;
    }
    const ref = m[2] ? parseInt(m[2], 10) : null;
    if (ref != null && ref >= 1 && ref <= sourceCount) {
      segments.push({ text: clause, source_refs: [ref], inference: false });
    } else {
      segments.push({ text: clause, source_refs: [], inference: true });
    }
    last = m.index + m[0].length;
  }
  const tail = text.slice(last).trim();
  if (tail) segments.push({ text: tail, source_refs: [], inference: true });
  return segments.length ? segments : [];
}

function renderMessageBody(bodyEl, m, name, row) {
  const { sources, segments } = messagePayload(m);
  bodyEl.innerHTML = "";

  if (segments.length > 0) {
    segments.forEach((seg) => {
      const clause = document.createElement("span");
      clause.className = "msg-clause";
      clause.textContent = seg.text;
      bodyEl.appendChild(clause);

      const refs = seg.source_refs || [];
      if (refs.length > 0) {
        refs.forEach((ref) => {
          const src = sources[ref - 1];
          if (!src) return;
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "cite-mark";
          btn.textContent = `[${ref}]`;
          btn.title = "查看這句話依據的資料";
          btn.addEventListener("click", (e) => {
            e.stopPropagation();
            document
              .querySelectorAll(".msg-row--ref-active")
              .forEach((el) => el.classList.remove("msg-row--ref-active"));
            row.classList.add("msg-row--ref-active");
            fillSourcesDrawer(name, [src], {
              highlight: `依據：${seg.text.slice(0, 80)}`,
            });
            openSourcesDrawer(true);
          });
          bodyEl.appendChild(btn);
        });
      } else if (seg.inference) {
        const inf = document.createElement("span");
        inf.className = "cite-inference";
        inf.textContent = "［推論］";
        bodyEl.appendChild(inf);
      }
    });
    return;
  }

  bodyEl.textContent = m.content ?? "";
}

function resetSourcesDrawerHint() {
  const hint = document.getElementById("sourcesDrawerHint");
  if (hint) hint.textContent = "點選句尾的 [1][2] 查看該句依據哪段資料";
}

function fillSourcesDrawer(titleName, sources, opts = {}) {
  const body = document.getElementById("sourcesDrawerBody");
  const hint = document.getElementById("sourcesDrawerHint");
  const n = sources.length;
  const highlight = opts.highlight || "";
  if (hint) {
    hint.textContent = highlight
      ? highlight
      : n === 1
        ? `${titleName} · 這句話的依據`
        : `${titleName} · 這句話的依據（${n} 份）`;
  }
  if (!body) return;

  body.innerHTML = "";

  const intro = document.createElement("p");
  intro.className = "sources-intro";
  intro.textContent = highlight
    ? `${titleName}：${highlight}`
    : n === 1
      ? `${titleName} 的這段話，依據以下公開資料（知識庫檢索）。`
      : `${titleName} 的這段話，依據以下 ${n} 份公開資料。`;
  body.appendChild(intro);

  const listTitle = document.createElement("div");
  listTitle.className = "sources-title";
  listTitle.textContent = "資料清單";
  body.appendChild(listTitle);

  sources.forEach((s, i) => {
    const card = document.createElement("article");
    card.className = "source-card";

    const head = document.createElement("div");
    head.className = "source-card-head";

    const idx = document.createElement("span");
    idx.className = "source-index";
    idx.textContent = String(i + 1);
    head.appendChild(idx);

    const titles = document.createElement("div");
    titles.className = "source-card-titles";
    const strong = document.createElement("strong");
    strong.textContent = String(s.title || "未命名資料").slice(0, 200);
    titles.appendChild(strong);

    const tags = document.createElement("div");
    tags.className = "source-tags";
    const typePill = document.createElement("span");
    typePill.className = "source-pill";
    typePill.textContent = humanSourceType(s.source_type);
    tags.appendChild(typePill);
    titles.appendChild(tags);
    head.appendChild(titles);
    card.appendChild(head);

    const quote = document.createElement("blockquote");
    quote.className = "source-quote";
    quote.textContent = truncateQuote(s.content);
    card.appendChild(quote);

    if (s.source_url) {
      const a = document.createElement("a");
      a.className = "source-link";
      a.href = s.source_url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.textContent = "前往原文";
      card.appendChild(a);
    }
    body.appendChild(card);
  });
}

function openSourcesDrawer(open) {
  const drawer = document.getElementById("sourcesDrawer");
  const btn = document.getElementById("sourcesDrawerToggle");
  if (!drawer || !btn) return;
  drawer.classList.toggle("sources-drawer--open", open);
  btn.setAttribute("aria-expanded", open ? "true" : "false");
}


function clearSourcesDrawer() {
  const body = document.getElementById("sourcesDrawerBody");
  if (body) body.innerHTML = "";
  openSourcesDrawer(false);
  resetSourcesDrawerHint();
  document.querySelectorAll(".msg-row--ref-active").forEach((el) =>
    el.classList.remove("msg-row--ref-active")
  );
}

function appendMessageBubble(m) {
  const box = document.getElementById("chatMessages");
  const empty = box.querySelector(".empty");
  if (empty) empty.remove();

  const user = isUserMessage(m) && !isGuestMessage(m);
  const guest = isGuestMessage(m);
  const userTwin = isUserTwinMessage(m);
  const conclusion = isConclusionMessage(m);
  const directReply = !!m.direct_reply;
  const name = speakerName(m);
  const directTargetSlug =
    directReply && m.reply_to && m.reply_to !== "all" ? m.reply_to : "";
  const slug = m.person_slug || m.role || directTargetSlug || "";

  if (directReply) {
    removeDirectReplyPreview();
  }

  const row = document.createElement("div");
  let rowClass = "msg-row ";
  if (user) rowClass += "msg-row--user";
  else if (guest) rowClass += "msg-row--guest";
  else if (userTwin) rowClass += "msg-row--user-twin";
  else if (conclusion) rowClass += "msg-row--conclusion";
  else rowClass += "msg-row--assistant";
  if (directReply && !user && !guest && !conclusion) {
    rowClass += " msg-row--direct-reply";
  }
  row.className = rowClass;

  const avatarSlot = document.createElement("div");
  avatarSlot.className = "msg-avatar-slot";
  if (user || userTwin) {
    avatarSlot.appendChild(
      avatarEl(
        accountDisplayName(),
        profile?.avatar_url ? "avatar user-photo" : "avatar user-avatar",
        "",
        profile?.avatar_url || ""
      )
    );
  } else if (guest) {
    const av = document.createElement("div");
    av.className = "avatar guest-avatar";
    av.textContent = initials(name);
    avatarSlot.appendChild(av);
  } else if (conclusion) {
    const av = document.createElement("div");
    av.className = "avatar conclusion-avatar";
    av.textContent = "結";
    avatarSlot.appendChild(av);
  } else {
    const avUrl =
      m.avatar_url || personAvatarUrl(slug) || memberAvatarFromSession(slug);
    avatarSlot.appendChild(avatarEl(name, "avatar", slug, avUrl));
  }
  row.appendChild(avatarSlot);

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";

  const who = document.createElement("div");
  who.className = "msg-who";
  const engineTag = m.engine === "crewai" ? " · CrewAI" : "";
  const replyTag =
    user && m.reply_to && m.reply_to !== "all"
      ? ` → ${chatReplyTargetLabel(m.reply_to)}`
      : "";
  let phaseTag = "";
  if (m.interjection_index && m.interjection_total) {
    phaseTag = ` · 第 ${m.interjection_index}/${m.interjection_total} 位`;
  } else if (m.phase === "opening") phaseTag = " · 開場";
  else if (userTwin && m.phase === "debate") phaseTag = " · 總結辯論";
  else if (m.phase === "debate") phaseTag = " · 辯論";
  if (!user && !guest && !conclusion && directReply) {
    phaseTag += " · 回覆你";
  }
  who.textContent = `${name}${replyTag}${phaseTag}${engineTag}`;
  bubble.appendChild(who);

  if (!user && !guest && !conclusion && directReply) {
    const directBadge = document.createElement("div");
    directBadge.className = "msg-direct-reply-badge";
    const badgeAvatar = avatarEl(
      name,
      "avatar sm msg-direct-reply-badge-avatar",
      slug,
      m.avatar_url || personAvatarUrl(slug) || memberAvatarFromSession(slug)
    );
    const badgeText = document.createElement("span");
    badgeText.textContent = "正在回覆你";
    directBadge.appendChild(badgeAvatar);
    directBadge.appendChild(badgeText);
    bubble.appendChild(directBadge);
  }

  const body = document.createElement("div");
  body.className = "msg-body";
  renderMessageBody(body, m, name, row);
  bubble.appendChild(body);

  const { sources, segments } = messagePayload(m);
  if (!user && !conclusion && sources.length > 0 && segments.length === 0) {
    const foot = document.createElement("button");
    foot.type = "button";
    foot.className = "msg-ref-footnote";
    const label = refsFootnoteLabel(sources.length);
    foot.setAttribute("aria-label", `查看${name}${label}`);
    foot.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg><span>${escapeHtml(label)}</span>`;
    foot.addEventListener("click", (e) => {
      e.stopPropagation();
      document
        .querySelectorAll(".msg-row--ref-active")
        .forEach((el) => el.classList.remove("msg-row--ref-active"));
      row.classList.add("msg-row--ref-active");
      fillSourcesDrawer(name, sources);
      openSourcesDrawer(true);
      document.getElementById("sourcesDrawer")?.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    });
    bubble.appendChild(foot);
  }

  row.appendChild(bubble);
  box.appendChild(row);
  box.scrollTop = box.scrollHeight;

  // User sent a directed interjection: immediately show left-side target preview.
  if (user && m.pending_direct_reply && m.reply_to && m.reply_to !== "all") {
    appendDirectReplyPreview(m.reply_to);
  }

  if (
    typeof scheduleInsightsLiveUpdate === "function" &&
    (m.person_slug || userTwin || conclusion)
  ) {
    scheduleInsightsLiveUpdate(true);
  }

  return row;
}

/** 插話「所有人」：依後端排序一位一位顯示，避免一次跳出多人 */
async function revealInterjectionRound(replies, speakingOrder) {
  const list = replies || [];
  if (!list.length) return;
  const order = speakingOrder || [];
  const gap = typeof TURN_GAP_MS !== "undefined" ? TURN_GAP_MS : 750;
  const total = list.length;
  const baseVisible = visibleChatMessageCount();

  for (let i = 0; i < list.length; i++) {
    const m = list[i];
    const slot = order[i] || {};
    const name = slot.name_zh || m.person_name_zh || "發言者";
    const slug = slot.person_slug || m.person_slug || "";
    const kind = slot.kind === "user_twin" || m.role === "user_twin" ? "user_twin" : "celeb";

    showTypingIndicator({
      name_zh: name,
      person_slug: slug,
      avatar_url: slot.avatar_url || m.avatar_url || "",
      kind,
      phase: "debate",
    });
    setDiscussSubtitle(`第 ${i + 1}/${total} 位 · ${name} 思考中…`);

    if (typeof refreshInsightsWhileThinking === "function") {
      try {
        await refreshInsightsWhileThinking(baseVisible + i);
      } catch {
        /* ignore live insights failures */
      }
    }
    await sleep(480);
    removeTypingIndicator();
    appendMessageBubble(m);

    const box = document.getElementById("chatMessages");
    if (box) box.scrollTop = box.scrollHeight;
    if (i < list.length - 1) await sleep(gap);
  }
}

function renderMessages(messages) {
  const box = document.getElementById("chatMessages");
  box.innerHTML = "";
  const members = currentSession?.members || [];
  if (!messages.length) {
    const names = members.map((m) => m.name_zh).join("、");
    const me = accountDisplayName();
    box.innerHTML = `<p class="empty">主題討論室${names ? ` · ${escapeHtml(names)}` : ""}。進入後會自動依序討論；你可隨時插話。句尾 [1][2] 可查看該句依據。</p>`;
    return;
  }
  for (const m of messages) appendMessageBubble(m);
}

function removeDirectReplyPreview() {
  document.getElementById("directReplyPreview")?.remove();
}

function appendDirectReplyPreview(targetId) {
  removeDirectReplyPreview();
  if (!targetId || targetId === "all") return;

  const box = document.getElementById("chatMessages");
  if (!box) return;
  const empty = box.querySelector(".empty");
  if (empty) empty.remove();

  const meta = chatReplyTargetMeta(targetId);
  const name = meta.label || "名人";
  const slug = meta.slug || targetId;
  const avUrl = meta.avatarUrl || personAvatarUrl(slug) || memberAvatarFromSession(slug);

  const row = document.createElement("div");
  row.id = "directReplyPreview";
  row.className = "msg-row msg-row--assistant msg-row--direct-reply-preview";

  const avatarSlot = document.createElement("div");
  avatarSlot.className = "msg-avatar-slot";
  avatarSlot.appendChild(avatarEl(name, "avatar", slug, avUrl));
  row.appendChild(avatarSlot);

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble msg-bubble--direct-reply-preview";

  const who = document.createElement("div");
  who.className = "msg-who";
  who.textContent = `${name} · 回覆中`;
  bubble.appendChild(who);

  const body = document.createElement("div");
  body.className = "msg-body msg-body--typing";
  const label = document.createElement("span");
  label.className = "typing-label";
  label.textContent = "正在回覆你";
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

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function stopAutoDiscussion() {
  resetTurnLock();
}

function setDiscussSubtitle(text) {
  const el = document.getElementById("chatSubtitle");
  if (el && text) el.textContent = text;
}

function defaultDiscussSubtitle() {
  const members = currentSession?.members || [];
  return members.length > 1
    ? `分身開場 → ${members.length} 位名人開場 → 辯論 → 分身總結 → 結論`
    : "分身開場 → 名人 → 辯論 → 分身總結 → 結論";
}

async function waitTurnIdle(maxMs = 120000) {
  const deadline = Date.now() + maxMs;
  while (turnInFlight) {
    if (Date.now() > deadline) {
      resetTurnLock();
      break;
    }
    await sleep(80);
  }
}

