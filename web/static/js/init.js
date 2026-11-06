/* js/init.js — 事件綁定與啟動 */
document.getElementById("btnCreate")?.addEventListener("click", () => {
  openCreateModal({ slugs: [], topic: "" });
});

document.getElementById("btnJoin")?.addEventListener("click", openJoinModal);
document.getElementById("btnJoinCancel")?.addEventListener("click", closeJoinModal);
document.getElementById("btnJoinConfirm")?.addEventListener("click", joinRoom);
document.getElementById("joinCode")?.addEventListener("input", previewJoinCode);
document.getElementById("joinModal")?.addEventListener("click", (e) => {
  if (e.target.id === "joinModal") closeJoinModal();
});

document.getElementById("roomTopic")?.addEventListener("input", () => {
  updateModalSelection();
  if (!topicRecommendDisabled) scheduleTopicRecommendations();
});
document.getElementById("modalPersonSearch")?.addEventListener("input", () => {
  renderModalPersons();
});

document.getElementById("btnCreateRoomAttach")?.addEventListener("click", () => {
  document.getElementById("createRoomFiles")?.click();
});

document.getElementById("createRoomFiles")?.addEventListener("change", (e) => {
  const picked = [...(e.target.files || [])];
  e.target.value = "";
  if (!picked.length) return;
  const room = CREATE_ROOM_MAX_FILES - createRoomPendingFiles.length;
  if (room <= 0) {
    alert(`最多上傳 ${CREATE_ROOM_MAX_FILES} 個參考檔`);
    return;
  }
  if (picked.length > room) {
    alert(`最多再上傳 ${room} 個檔案（合計 ${CREATE_ROOM_MAX_FILES} 個）`);
  }
  createRoomPendingFiles.push(...picked.slice(0, room));
  renderCreateRoomAttachPreview();
  updateModalSelection();
});

function isAllowGuestJoin() {
  return document.getElementById("btnAllowJoin")?.classList.contains("allow-on");
}

function setAllowJoinUI(allow) {
  const allowBtn = document.getElementById("btnAllowJoin");
  const extras = document.getElementById("createRoomJoinExtras");
  const pwdBtn = document.getElementById("btnUsePassword");
  const pwdInput = document.getElementById("roomPassword");
  if (!allowBtn) return;

  allowBtn.classList.toggle("allow-on", allow);
  allowBtn.classList.toggle("allow-off", !allow);
  allowBtn.setAttribute("aria-pressed", allow ? "true" : "false");

  const label = allowBtn.querySelector(".modal-allow-join-text");
  const icon = allowBtn.querySelector(".modal-allow-join-icon");
  if (label) label.textContent = allow ? "允許加入" : "不開放加入";
  if (icon) icon.textContent = allow ? "✓" : "✕";

  extras?.classList.toggle("hidden", !allow);

  pwdBtn?.classList.remove("active");
  pwdBtn?.setAttribute("aria-pressed", "false");
  pwdInput?.classList.add("hidden");
  if (pwdInput) pwdInput.value = "";
}

function resetCreateRoomSettings() {
  setAllowJoinUI(true);
}

function syncCreateRoomSettingsUI() {
  const pwdBtn = document.getElementById("btnUsePassword");
  const pwdInput = document.getElementById("roomPassword");
  if (!isAllowGuestJoin()) {
    pwdInput?.classList.add("hidden");
    return;
  }

  if (pwdBtn?.classList.contains("active")) {
    pwdInput?.classList.remove("hidden");
    pwdInput?.focus();
  } else {
    pwdInput?.classList.add("hidden");
  }
}

document.getElementById("btnAllowJoin")?.addEventListener("click", () => {
  setAllowJoinUI(!isAllowGuestJoin());
});

document.getElementById("btnUsePassword")?.addEventListener("click", () => {
  const btn = document.getElementById("btnUsePassword");
  if (btn.hasAttribute("disabled")) return;
  const on = !btn.classList.contains("active");
  btn.classList.toggle("active", on);
  btn.setAttribute("aria-pressed", on ? "true" : "false");
  if (!on) document.getElementById("roomPassword").value = "";
  syncCreateRoomSettingsUI();
});

document.getElementById("btnStartRoom")?.addEventListener("click", async () => {
  const topic = (document.getElementById("roomTopic")?.value || "").trim();
  const startBtn = document.getElementById("btnStartRoom");
  if (selectedSlugs.size < 1) {
    alert("請至少選擇一位名人");
    return;
  }
  if (!topic) {
    alert("請輸入討論主題");
    return;
  }
  if (!isAuthenticated) {
    alert("請先登入後再建立討論室");
    showAuthGate();
    return;
  }
  const prevLabel = startBtn?.textContent;
  if (startBtn) {
    startBtn.disabled = true;
    startBtn.textContent = "建立中…";
  }
  try {
    const allowGuestJoin = isAllowGuestJoin();
    const usePassword =
      allowGuestJoin &&
      document.getElementById("btnUsePassword")?.classList.contains("active");
    const roomPassword = usePassword
      ? (document.getElementById("roomPassword")?.value || "").trim()
      : "";
    await createRoom([...selectedSlugs], topic, {
      allowGuestJoin,
      roomPassword,
    });
    closeCreateModal();
  } catch (e) {
    alert(e.message || "建立討論室失敗");
  } finally {
    if (startBtn) {
      startBtn.textContent = prevLabel || "開始討論";
      updateModalSelection();
    }
  }
});

document.getElementById("createModal").addEventListener("click", (e) => {
  if (e.target.id === "createModal") closeCreateModal();
});

document.getElementById("btnPersonProfileCloseX")?.addEventListener("click", closePersonProfileModal);
document.getElementById("btnPersonProfileChat")?.addEventListener("click", () => {
  const person = profilePerson ? { ...profilePerson } : null;
  if (!person?.slug) return;
  closePersonProfileModal();
  showPersonChat(person);
});
document.getElementById("personProfileModal")?.addEventListener("click", (e) => {
  if (e.target.id === "personProfileModal") closePersonProfileModal();
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const userModal = document.getElementById("userProfileModal");
  if (userModal?.classList.contains("is-shown")) {
    closeUserProfileModal();
    return;
  }
  closePersonProfileModal();
});

document.getElementById("btnBack").addEventListener("click", showDiscover);

document.getElementById("personSearch").addEventListener("input", (e) => {
  globalSearchQuery = e.target.value;
  renderDiscoverFeed();
});

document.getElementById("historySearch").addEventListener("input", (e) => {
  renderHistory(e.target.value);
});

document.querySelectorAll(".nav-item").forEach((item) => {
  item.addEventListener("click", () => {
    const nav = item.dataset.nav;
    if (nav === "create-twin") {
      openCreateTwinModal();
      return;
    }
    document.querySelectorAll(".nav-item").forEach((n) => n.classList.remove("active"));
    item.classList.add("active");
    if (nav === "discover") showDiscover();
    else if (nav === "twin-chat") showTwinChat();
    else if (nav === "labs") {
      if (typeof showMediaLibraryHome === "function") showMediaLibraryHome();
      else window.location.href = "/lab";
    }
    else if (sessions[0]) openSession(sessions[0].id);
    else alert("此功能即將推出");
  });
});

document.getElementById("sourcesDrawerToggle")?.addEventListener("click", () => {
  const drawer = document.getElementById("sourcesDrawer");
  const body = document.getElementById("sourcesDrawerBody");
  const willOpen = !drawer.classList.contains("sources-drawer--open");
  openSourcesDrawer(willOpen);
  if (willOpen && body && body.childElementCount === 0) {
    body.innerHTML =
      '<p class="empty">請先點選名人回覆句尾的 [1]、[2] 標記</p>';
    resetSourcesDrawerHint();
  }
});

document.getElementById("chatForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const activeSessionId = currentSessionId || currentSession?.id || null;
  if (!activeSessionId) {
    setDiscussSubtitle("尚未進入有效聊天室，請重新開啟該房間");
    alert("尚未進入有效聊天室，訊息不會寫入資料庫。請先重新點選左側房間。");
    return;
  }
  if (!currentSessionId) currentSessionId = activeSessionId;

  const input = document.getElementById("chatInput");
  const btn = document.getElementById("btnSend");
  const text = (input?.value || "").trim();
  if (!text || !input || !btn) return;

  const replyTo = getChatReplyTarget();
  const isDirect = replyTo !== "all";
  const pendingUserMessage = {
    role: "user",
    content: text,
    reply_to: replyTo,
  };

  // 直接先顯示本地泡泡，讓送出狀態可見；失敗再回滾。
  const pendingUserRow = appendMessageBubble({
    ...pendingUserMessage,
    pending_local: true,
  });

  input.value = "";
  btn.disabled = true;
  window.__directReplyInFlight = isDirect;
  stopAutoDiscussion();
  if (typeof resetTurnLock === "function") resetTurnLock();

  const safeRemoveDirectPreview = () => {
    if (typeof removeDirectReplyPreview === "function") removeDirectReplyPreview();
    else document.getElementById("directReplyPreview")?.remove();
  };

  if (isDirect) {
    setDiscussSubtitle(`等待 ${chatReplyTargetLabel(replyTo)} 回覆…`);
    if (typeof appendDirectReplyPreview === "function") appendDirectReplyPreview(replyTo);
  } else {
    setDiscussSubtitle("插話後一輪討論中…");
    showTypingIndicator({
      name_zh: "與會名人",
      person_slug: "",
      kind: "celeb",
      phase: "debate",
    });
  }

  try {
    const data = await fetchJson(
      `/api/sessions/${activeSessionId}/messages`,
      {
        method: "POST",
        body: JSON.stringify({ content: text, reply_to: replyTo }),
      },
      activeSessionId
    );
    const effectiveReplyTo = data.reply_to || replyTo;

    if (pendingUserRow?.parentNode) pendingUserRow.remove();
    appendMessageBubble({
      ...(data.user_message || pendingUserMessage),
      reply_to: effectiveReplyTo,
    });

    if (data.user_message?.id) {
      setDiscussSubtitle(`已送出（#${data.user_message.id}）`);
    }

    if (data.replies?.length) {
      removeTypingIndicator();
      safeRemoveDirectPreview();
      if (data.follow_up === "round") {
        await revealInterjectionRound(data.replies, data.speaking_order);
        setDiscussSubtitle("一輪討論完成（依序回覆）");
      } else {
        const m = data.replies[0];
        appendMessageBubble({
          ...m,
          direct_reply: true,
          reply_to: effectiveReplyTo,
          person_slug:
            m.person_slug || (effectiveReplyTo === "user_twin" ? "" : effectiveReplyTo),
          avatar_url: m.avatar_url || "",
        });
        setDiscussSubtitle(`已回覆：${chatReplyTargetLabel(effectiveReplyTo)}`);
      }
      await refreshTurnUi();
    } else {
      removeTypingIndicator();
      safeRemoveDirectPreview();
      if (data.follow_up_error) {
        alert(data.follow_up_error);
      } else {
        const access = getAccessForSession(activeSessionId);
        if (access.isOwner && data.awaiting_turn) runAutoDiscussion();
      }
    }
  } catch (err) {
    if (pendingUserRow?.parentNode) pendingUserRow.remove();
    removeTypingIndicator();
    safeRemoveDirectPreview();
    setDiscussSubtitle("送出失敗（未寫入資料庫），請再試一次");
    alert(`送出失敗，訊息未寫入資料庫：${err.message}`);
  } finally {
    window.__directReplyInFlight = false;
    safeRemoveDirectPreview();
    btn.disabled = false;
    input.focus();
  }
});

document.getElementById("btnNotify")?.addEventListener("click", (e) => {
  e.stopPropagation();
  toggleNotifyDropdown();
});

document.addEventListener("click", (e) => {
  const wrap = document.getElementById("notifyWrap");
  if (!wrap || wrap.contains(e.target)) return;
  closeNotifyDropdown();
});

document.getElementById("createTwinModalForm")?.addEventListener("submit", submitCreateTwinModal);
document.getElementById("createTwinModalClose")?.addEventListener("click", closeCreateTwinModal);
document.getElementById("createTwinModal")?.addEventListener("click", (e) => {
  if (e.target.id === "createTwinModal") closeCreateTwinModal();
});
document.getElementById("btnEditProfile")?.addEventListener("click", openProfileSettings);
document.getElementById("btnUserProfileCloseX")?.addEventListener("click", closeUserProfileModal);
document.getElementById("userProfileModal")?.addEventListener("click", (e) => {
  if (e.target.id === "userProfileModal") closeUserProfileModal();
});
document.getElementById("profileEditForm")?.addEventListener("submit", submitProfileEdit);
document.getElementById("profileViewAvatar")?.addEventListener("click", openProfileAvatarPicker);
document.getElementById("profileViewAvatar")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    openProfileAvatarPicker();
  }
});
document.getElementById("profileAvatarInput")?.addEventListener("change", handleProfileAvatarInputChange);
document.getElementById("twinCreatePreset")?.addEventListener("change", (e) => {
  const preset = e.target.value;
  const nameInput = document.getElementById("twinCreateName");
  applyTwinNameRule(nameInput, preset);
});
document.getElementById("createTwinModalPresetButtons")?.addEventListener("change", (e) => {
  const target = e.target;
  if (!(target instanceof HTMLInputElement)) return;
  if (target.name !== "createTwinModalPreset") return;
  const preset = target.value;
  createTwinModalStep = 1;
  const nameInput = document.getElementById("createTwinModalName");
  applyTwinNameRule(nameInput, preset);
  refreshCreateTwinModalLayout();
});
document.getElementById("createTwinStudentEducation")?.addEventListener("change", () => {
  updateStudentGradeOptions();
});
document.getElementById("createTwinStyleCard")?.addEventListener("click", (e) => {
  const btn = e.target.closest(".create-twin-style-option");
  if (!btn) return;
  const question = btn.closest(".create-twin-style-question");
  if (!question) return;
  question.querySelectorAll(".create-twin-style-option").forEach((node) => {
    node.classList.remove("active");
  });
  btn.classList.add("active");
});
document.getElementById("createTwinUploadTags")?.addEventListener("click", (e) => {
  const btn = e.target.closest(".create-twin-upload-tag");
  if (!btn) return;
  btn.classList.toggle("active");
});
document.getElementById("createTwinUploadInput")?.addEventListener("change", (e) => {
  const picked = Array.from(e.target.files || []);
  if (!picked.length) return;
  createTwinUploadFiles.push(...picked);
  renderCreateTwinUploadList("createTwinUploadList", createTwinUploadFiles);
  e.target.value = "";
});
document.getElementById("createTwinUploadList")?.addEventListener("click", (e) => {
  const btn = e.target.closest(".create-twin-upload-remove");
  if (!btn) return;
  const idx = Number(btn.dataset.uploadIndex || -1);
  if (!Number.isFinite(idx) || idx < 0 || idx >= createTwinUploadFiles.length) return;
  createTwinUploadFiles.splice(idx, 1);
  renderCreateTwinUploadList("createTwinUploadList", createTwinUploadFiles);
});
document.getElementById("createTwinProjectUploadTags")?.addEventListener("click", (e) => {
  const btn = e.target.closest(".create-twin-upload-tag");
  if (!btn) return;
  btn.classList.toggle("active");
});
document.getElementById("createTwinProjectUploadInput")?.addEventListener("change", (e) => {
  const picked = Array.from(e.target.files || []);
  if (!picked.length) return;
  createTwinProjectUploadFiles.push(...picked);
  renderCreateTwinUploadList("createTwinProjectUploadList", createTwinProjectUploadFiles);
  e.target.value = "";
});
document.getElementById("createTwinProjectUploadList")?.addEventListener("click", (e) => {
  const btn = e.target.closest(".create-twin-upload-remove");
  if (!btn) return;
  const idx = Number(btn.dataset.uploadIndex || -1);
  if (!Number.isFinite(idx) || idx < 0 || idx >= createTwinProjectUploadFiles.length) return;
  createTwinProjectUploadFiles.splice(idx, 1);
  renderCreateTwinUploadList("createTwinProjectUploadList", createTwinProjectUploadFiles);
});
document.getElementById("btnCreateTwinModalNext")?.addEventListener("click", proceedCreateTwinModalStep);
document.getElementById("btnCreateTwinModalBack")?.addEventListener("click", () => {
  goCreateTwinModalStep(Math.max(1, createTwinModalStep - 1));
});

document.getElementById("profileBox")?.addEventListener("click", (e) => {
  e.stopPropagation();
  toggleProfileMenu();
});

document.getElementById("insightsPanelToggle")?.addEventListener("click", () => toggleInsightsPanel());
document.getElementById("btnInsightsTop")?.addEventListener("click", () => toggleInsightsPanel());
document.getElementById("btnInsightsRefresh")?.addEventListener("click", () => scheduleInsightsRefresh(true));

document.getElementById("btnLogout")?.addEventListener("click", logout);

document.addEventListener("click", (e) => {
  const menu = document.getElementById("profileMenu");
  const box = document.getElementById("profileBox");
  if (!menu || menu.classList.contains("hidden")) return;
  if (menu.contains(e.target) || box?.contains(e.target)) return;
  closeProfileMenu();
});

document.querySelectorAll(".auth-tab").forEach((btn) => {
  btn.addEventListener("click", () => setAuthTab(btn.dataset.authTab));
});
document.getElementById("loginForm")?.addEventListener("submit", submitLogin);
document.getElementById("registerForm")?.addEventListener("submit", submitRegister);
document.getElementById("btnAuthGoogle")?.addEventListener("click", () => submitSocialAuth("google"));
document.getElementById("btnAuthApple")?.addEventListener("click", () => submitSocialAuth("apple"));
document.getElementById("guestJoinForm")?.addEventListener("submit", submitGuestJoinFromAuth);
document.getElementById("btnShowGuestJoin")?.addEventListener("click", showGuestJoinOnAuth);
document.getElementById("btnBackToAuth")?.addEventListener("click", () => {
  showAuthError("guestJoinError", "");
  setAuthTab("login");
});

document.getElementById("btnTwinAttach")?.addEventListener("click", () => {
  document.getElementById("twinFileInput")?.click();
});
document.getElementById("twinFileInput")?.addEventListener("change", (e) => {
  const files = Array.from(e.target.files || []);
  twinPendingFiles.push(...files);
  renderTwinAttachPreview();
  e.target.value = "";
});
document.getElementById("twinChatForm")?.addEventListener("submit", sendTwinMessage);
document.getElementById("btnTwinMic")?.addEventListener("click", () => {
  alert("語音輸入即將推出");
});

document.getElementById("btnStancePhaseClose")?.addEventListener("click", closeStancePhaseModal);
document.getElementById("stancePhaseModal")?.addEventListener("click", (e) => {
  if (e.target.id === "stancePhaseModal") closeStancePhaseModal();
});

initChatReplyPicker();

(async function init() {
  try {
    const authed = await checkAuth();
    if (authed) {
      await loadPersons();
      await loadSessions();
      startNotifyPolling();
    }
  } catch (e) {
    console.error(e);
    showAuthGate();
    showAuthError("loginError", "無法連線後端，請確認 uvicorn 已啟動");
  }
})();
