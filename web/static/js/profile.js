/* js/profile.js */
async function loadProfile() {
  profile = await fetchJson("/api/profile");
  applyProfileUI(profile);
}

let twinPendingFiles = [];
let twinChatSending = false;
let twinChatVisible = false;
let twinChatMode = "twin";
let twinChatPerson = null;
let createTwinModalStep = 1;
let createTwinUploadFiles = [];
let createTwinProjectUploadFiles = [];

const TWIN_PRESET_HINTS = {
  life: "分享生活點滴，讓我更了解你",
  student: "聊聊課業與學習，我會記住你的方向",
  company: "討論工作與職涯，我會以專業模式回應",
  custom: "隨意聊聊，我會慢慢認識你",
};

const TWIN_PRESET_LABELS = {
  life: "生活",
  student: "學生",
  company: "公司",
  custom: "自訂",
};
const STUDENT_FIELD_IDS = [
  "createTwinStudentEducation",
  "createTwinStudentUniversity",
  "createTwinStudentGrade",
  "createTwinStudentMajor",
  "createTwinStudentSkills",
  "createTwinStudentIntro",
];
const COMPANY_FIELD_IDS = [
  "createTwinCompanyIndustry",
  "createTwinCompanyRoleLevel",
  "createTwinCompanyName",
  "createTwinCompanyDepartment",
  "createTwinCompanyTitle",
  "createTwinCompanySkills",
  "createTwinCompanyIntro",
];
const LIFE_FIELD_IDS = [
  "createTwinLifeStage",
  "createTwinLifeRhythm",
  "createTwinLifeCity",
  "createTwinLifeInterests",
  "createTwinLifeGoals",
  "createTwinLifeStressRelief",
  "createTwinLifeIntro",
];
const CUSTOM_FIELD_IDS = [
  "createTwinCustomRole",
  "createTwinCustomTone",
  "createTwinCustomDomain",
  "createTwinCustomBoundaries",
  "createTwinCustomGoal",
  "createTwinCustomKeywords",
  "createTwinCustomIntro",
];
const STUDENT_EDUCATION_LABELS = {
  elementary: "國小",
  junior: "國中",
  senior: "高中",
  university: "大學",
  master: "碩士",
};
const COMPANY_INDUSTRY_LABELS = {
  tech: "科技 / 軟體",
  finance: "金融 / 保險",
  education: "教育 / 研究",
  healthcare: "醫療 / 生技",
  manufacturing: "製造 / 供應鏈",
  service: "服務 / 零售",
  other: "其他",
};
const COMPANY_ROLE_LABELS = {
  intern: "實習 / 初階",
  staff: "一般職員",
  lead: "資深 / 組長",
  manager: "主管 / 經理",
  director: "總監 / 高階主管",
  founder: "創辦人 / 合夥人",
};
const LIFE_STAGE_LABELS = {
  student: "學生生活",
  "new-grad": "新鮮人 / 社會新鮮人",
  working: "上班族",
  freelancer: "自由工作者",
  family: "家庭照顧者",
  other: "其他",
};
const LIFE_RHYTHM_LABELS = {
  morning: "晨型（早睡早起）",
  mixed: "混合型（依工作調整）",
  night: "夜型（晚睡晚起）",
  irregular: "不固定",
};
const CUSTOM_ROLE_LABELS = {
  mentor: "導師型（給建議、給方向）",
  partner: "夥伴型（一起討論、共創）",
  executor: "執行型（拆解任務、推進進度）",
  listener: "陪伴型（傾聽、整理情緒）",
  other: "其他",
};
const CUSTOM_TONE_LABELS = {
  concise: "精簡直接",
  balanced: "平衡清楚",
  detailed: "完整詳細",
  friendly: "溫和鼓勵",
};
const STUDENT_GRADE_OPTIONS = {
  elementary: ["一年級", "二年級", "三年級", "四年級", "五年級", "六年級"],
  junior: ["一年級", "二年級", "三年級"],
  senior: ["一年級", "二年級", "三年級"],
  university: ["一年級", "二年級", "三年級", "四年級", "五年級以上"],
  master: ["一年級", "二年級", "三年級以上"],
};
const TWIN_STYLE_QUESTION_IDS = ["decision", "priority", "speech", "conflict"];

function applyTwinNameRule(nameInput, preset) {
  if (!nameInput) return;
  const isCustom = preset === "custom";
  nameInput.required = isCustom;
  if (isCustom) {
    nameInput.placeholder = "請輸入自訂分身名稱";
    if (nameInput.value.trim() === TWIN_PRESET_LABELS.life ||
        nameInput.value.trim() === TWIN_PRESET_LABELS.student ||
        nameInput.value.trim() === TWIN_PRESET_LABELS.company) {
      nameInput.value = "";
    }
    return;
  }
  const presetLabel = TWIN_PRESET_LABELS[preset] || preset || "分身";
  nameInput.placeholder = `預設：${presetLabel}`;
  nameInput.value = presetLabel;
}

function getCreateTwinModalPresetValue() {
  const selected = document.querySelector(
    'input[name="createTwinModalPreset"]:checked'
  );
  return selected?.value || "custom";
}

function setCreateTwinStudentFieldsVisible(preset) {
  const host = document.getElementById("createTwinStudentFields");
  const isStudent = preset === "student";
  const showStudentPage = isStudent && createTwinModalStep === 1;
  host?.classList.toggle("hidden", !showStudentPage);
  if (showStudentPage) updateStudentGradeOptions();
}

function setCreateTwinCompanyFieldsVisible(preset) {
  const host = document.getElementById("createTwinCompanyFields");
  const showCompanyPage = preset === "company" && createTwinModalStep === 1;
  host?.classList.toggle("hidden", !showCompanyPage);
}

function setCreateTwinLifeFieldsVisible(preset) {
  const host = document.getElementById("createTwinLifeFields");
  const showLifePage = preset === "life" && createTwinModalStep === 1;
  host?.classList.toggle("hidden", !showLifePage);
}

function setCreateTwinCustomFieldsVisible(preset) {
  const host = document.getElementById("createTwinCustomFields");
  const showCustomPage = preset === "custom" && createTwinModalStep === 1;
  host?.classList.toggle("hidden", !showCustomPage);
}

function refreshCreateTwinModalLayout() {
  const preset = getCreateTwinModalPresetValue();
  const isGuidedPreset =
    preset === "student" || preset === "company" || preset === "life" || preset === "custom";
  const showProfileStep = isGuidedPreset && createTwinModalStep === 1;
  const hideCore = isGuidedPreset && createTwinModalStep >= 2;
  const core = document.getElementById("createTwinModalCoreFields");
  const extra = document.getElementById("createTwinModalExtraFields");
  const step2 = document.getElementById("createTwinStep2Fields");
  const step3 = document.getElementById("createTwinStep3Fields");
  const step4 = document.getElementById("createTwinStep4Fields");
  const btnBack = document.getElementById("btnCreateTwinModalBack");
  const btnNext = document.getElementById("btnCreateTwinModalNext");
  const btnConfirm = document.getElementById("btnCreateTwinModalConfirm");
  const footer = document.querySelector("#createTwinModal .modal-footer");
  core?.classList.toggle("hidden", hideCore);
  extra?.classList.toggle("hidden", !isGuidedPreset || showProfileStep);
  step2?.classList.toggle("hidden", !isGuidedPreset || createTwinModalStep !== 2);
  step3?.classList.toggle("hidden", !isGuidedPreset || createTwinModalStep !== 3);
  step4?.classList.toggle("hidden", !isGuidedPreset || createTwinModalStep !== 4);
  setCreateTwinStudentFieldsVisible(preset);
  setCreateTwinCompanyFieldsVisible(preset);
  setCreateTwinLifeFieldsVisible(preset);
  setCreateTwinCustomFieldsVisible(preset);
  btnBack?.classList.toggle("hidden", !isGuidedPreset || createTwinModalStep === 1);
  btnNext?.classList.toggle(
    "hidden",
    !isGuidedPreset ||
      (createTwinModalStep !== 1 &&
        createTwinModalStep !== 2 &&
        createTwinModalStep !== 3)
  );
  btnConfirm?.classList.toggle("hidden", isGuidedPreset && createTwinModalStep !== 4);
  footer?.classList.toggle(
    "create-twin-footer-step1",
    isGuidedPreset && createTwinModalStep === 1
  );
  if (btnConfirm) {
    btnConfirm.textContent = isGuidedPreset ? "儲存並完成設定" : "建立分身";
  }
}

function goCreateTwinModalStep(step) {
  createTwinModalStep = step <= 1 ? 1 : step >= 4 ? 4 : step;
  refreshCreateTwinModalLayout();
  if (createTwinModalStep === 2) {
    document
      .querySelector("#createTwinStyleCard .create-twin-style-option")
      ?.focus();
  } else if (createTwinModalStep === 3) {
    document.getElementById("createTwinUploadInput")?.focus();
  } else if (createTwinModalStep === 4) {
    document.getElementById("createTwinProjectUploadInput")?.focus();
  }
}

function updateStudentGradeOptions() {
  const eduEl = document.getElementById("createTwinStudentEducation");
  const gradeEl = document.getElementById("createTwinStudentGrade");
  if (!eduEl || !gradeEl) return;
  const selectedEdu = (eduEl.value || "").trim();
  const prevGrade = gradeEl.value;
  const gradeOptions = STUDENT_GRADE_OPTIONS[selectedEdu] || [];
  gradeEl.innerHTML = "";
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = selectedEdu ? "年級（請選擇）" : "年級（請先選學歷）";
  gradeEl.appendChild(placeholder);
  for (const g of gradeOptions) {
    const opt = document.createElement("option");
    opt.value = g;
    opt.textContent = g;
    gradeEl.appendChild(opt);
  }
  gradeEl.disabled = !selectedEdu;
  if (!gradeOptions.includes(prevGrade)) {
    gradeEl.value = "";
  } else {
    gradeEl.value = prevGrade;
  }
}

function resetTwinStyleAnswers() {
  document
    .querySelectorAll("#createTwinStyleCard .create-twin-style-option.active")
    .forEach((btn) => btn.classList.remove("active"));
}

function getTwinStyleAnswers() {
  const answers = {};
  document
    .querySelectorAll("#createTwinStyleCard .create-twin-style-question")
    .forEach((q) => {
      const key = q.dataset.styleQuestion || "";
      const active = q.querySelector(".create-twin-style-option.active");
      if (!key || !active) return;
      answers[key] = active.dataset.styleValue || active.textContent.trim();
    });
  return answers;
}

function renderCreateTwinUploadList(hostId, files) {
  const host = document.getElementById(hostId);
  if (!host) return;
  if (!files.length) {
    host.innerHTML = "";
    host.classList.add("hidden");
    return;
  }
  host.classList.remove("hidden");
  host.innerHTML = files
    .map(
      (f, idx) => `
      <div class="create-twin-upload-item">
        <span>${escapeHtml(f.name)} (${Math.max(1, Math.round(f.size / 1024))} KB)</span>
        <button type="button" class="create-twin-upload-remove" data-upload-index="${idx}">移除</button>
      </div>
    `
    )
    .join("");
}

async function uploadCreateTwinFiles(twinId, files) {
  if (!files.length) return;
  const fd = new FormData();
  for (const f of files) fd.append("files", f);
  const res = await fetch(`/api/twins/${twinId}/context-files`, {
    method: "POST",
    body: fd,
    credentials: "include",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const msg = Array.isArray(detail)
      ? detail.map((d) => d.msg || d).join(", ")
      : detail || res.statusText || "上傳分身資料失敗";
    throw new Error(msg);
  }
}

function preferredUserLabel(p = profile) {
  if (!p) return "你";
  const accountName = p.account_name || p.username || p.display_name || "你";
  const twins = p.twins || [];
  const activeTwin = twins.find((t) => t.is_active) || twins[0];
  const presetLabel = activeTwin
    ? TWIN_PRESET_LABELS[activeTwin.preset] || activeTwin.name || ""
    : "";
  if (presetLabel) return `${accountName}（${presetLabel}）`;
  return accountName;
}

function applyProfileUI(p) {
  if (!p) return;
  const accountName = p.account_name || "使用者";
  const activeTwin = (p.twins || []).find((t) => t.is_active) || (p.twins || [])[0];
  const presetLabel = activeTwin
    ? TWIN_PRESET_LABELS[activeTwin.preset] || activeTwin.name
    : null;
  const sidebarLabel = preferredUserLabel(p);
  document.getElementById("profileName").textContent = sidebarLabel;
  document.getElementById("welcomeName").textContent = accountName;
  document.getElementById("profileMenuName").textContent = accountName;
  document.getElementById("profileMenuEmail").textContent = p.email || p.username || "";
  const avatarName = activeTwin?.name || accountName;
  const letter = initials(avatarName);
  const avatarUrl = p.avatar_url || "";
  const profileAv = document.getElementById("profileAvatar");
  if (avatarUrl && profileAv) {
    const pImg = avatarEl(avatarName, "avatar sm user-photo", "", avatarUrl);
    pImg.id = "profileAvatar";
    profileAv.replaceWith(pImg);
  } else if (profileAv) {
    profileAv.textContent = letter;
  }
  renderTwinMenu(p.twins || [], p.active_twin_id);
  syncProfileEditForm(p);
  updateTwinCreatePresetOptions(p.twins || []);
}

function updateTwinCreatePresetOptions(twins, opts = {}) {
  const { forceEnabledPreset = "" } = opts;
  const used = new Set(
    (twins || [])
      .map((t) => t.preset)
      .filter((p) => p === "life" || p === "student" || p === "company")
  );
  const allOptions = ["life", "student", "company", "custom"];
  const modalHost = document.getElementById("createTwinModalPresetButtons");
  if (modalHost) {
    const prevModal = getCreateTwinModalPresetValue();
    modalHost.innerHTML = "";
    for (const value of allOptions) {
      const label = document.createElement("label");
      label.className = "register-preset-option";
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "createTwinModalPreset";
      input.value = value;
      const span = document.createElement("span");
      span.textContent = TWIN_PRESET_LABELS[value] || value;
      const isDisabledByUsed =
        value !== "custom" && used.has(value) && value !== forceEnabledPreset;
      if (isDisabledByUsed) {
        input.disabled = true;
        span.textContent = `${TWIN_PRESET_LABELS[value] || value}（已建立）`;
        label.classList.add("is-disabled");
      }
      label.appendChild(input);
      label.appendChild(span);
      modalHost.appendChild(label);
    }
    const nextPreset = Array.from(
      modalHost.querySelectorAll('input[name="createTwinModalPreset"]')
    ).some((node) => node.value === prevModal && !node.disabled)
      ? prevModal
      : (modalHost.querySelector('input[name="createTwinModalPreset"]:not(:disabled)')?.value ||
        "custom");
    const nextInput = modalHost.querySelector(
      `input[name="createTwinModalPreset"][value="${nextPreset}"]`
    );
    if (nextInput) nextInput.checked = true;
  }
  applyTwinNameRule(
    document.getElementById("createTwinModalName"),
    getCreateTwinModalPresetValue()
  );
  refreshCreateTwinModalLayout();
}

function syncProfileEditForm(p) {
  if (!p) return;
  const activeTwin = (p.twins || []).find((t) => t.is_active) || (p.twins || [])[0];
  const presetLabel = activeTwin
    ? TWIN_PRESET_LABELS[activeTwin.preset] || activeTwin.name
    : "";
  const nameInput = document.getElementById("profileEditDisplayName");
  const bioInput = document.getElementById("profileEditBio");
  if (nameInput && document.activeElement !== nameInput) {
    nameInput.value = p.account_name || "";
  }
  if (bioInput && document.activeElement !== bioInput) {
    bioInput.value = p.bio || "";
  }
  const usernameEl = document.getElementById("profileViewUsername");
  const emailEl = document.getElementById("profileViewEmail");
  const twinEl = document.getElementById("profileViewActiveTwin");
  const heroName = document.getElementById("profileViewDisplayName");
  const heroTwin = document.getElementById("profileViewTwinLabel");
  if (usernameEl) usernameEl.value = p.username || "";
  if (emailEl) emailEl.value = p.email || "";
  if (twinEl) {
    twinEl.value = activeTwin ? `${activeTwin.name}（${presetLabel}）` : "—";
  }
  if (heroName) heroName.textContent = p.account_name || "使用者";
  if (heroTwin) heroTwin.textContent = presetLabel ? `${presetLabel}分身` : "";
  renderProfileViewAvatar(p, activeTwin);
  const metaEl = document.getElementById("userProfileMeta");
  if (metaEl) {
    metaEl.innerHTML = `
      <span class="profile-meta-chip">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
        @${escapeHtml(p?.username || "")}
      </span>
      <span class="profile-meta-chip">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16v16H4z"/><path d="M22 6l-10 7L2 6"/></svg>
        ${escapeHtml(p?.email || "")}
      </span>
    `;
  }
}

function renderProfileViewAvatar(p, activeTwin) {
  const name = activeTwin?.name || p?.account_name || "使用者";
  const avatarUrl = p?.avatar_url || "";
  const hero = document.getElementById("userProfileHero");
  if (hero) {
    hero.classList.remove("has-photo");
    hero.style.removeProperty("--hero-photo");
    if (avatarUrl && !String(avatarUrl).includes("gradient")) {
      hero.style.setProperty("--hero-photo", `url("${avatarUrl}")`);
      hero.classList.add("has-photo");
    }
  }
  const host = document.getElementById("profileViewAvatar");
  if (!host) return;
  host.innerHTML = "";
  if (avatarUrl && !String(avatarUrl).includes("gradient")) {
    host.appendChild(avatarEl(name, "avatar lg user-photo", "", avatarUrl));
  } else {
    const av = document.createElement("div");
    av.className = "avatar lg";
    av.textContent = initials(name);
    host.appendChild(av);
  }
}

function showProfileSaveError(msg) {
  const el = document.getElementById("profileSaveError");
  if (!el) return;
  if (!msg) {
    el.textContent = "";
    el.classList.add("hidden");
    return;
  }
  el.textContent = msg;
  el.classList.remove("hidden");
}

async function uploadProfileAvatarFile(file) {
  if (!file) return null;
  const form = new FormData();
  form.append("file", file);
  const res = await fetch("/api/profile/avatar", {
    method: "POST",
    body: form,
    credentials: "include",
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = Array.isArray(data.detail)
      ? data.detail.map((d) => d.msg || d).join(", ")
      : data.detail || res.statusText || "頭像上傳失敗";
    throw new Error(msg);
  }
  return data;
}

async function handleProfileAvatarInputChange(e) {
  const input = e?.target;
  const file = input?.files?.[0];
  if (!file) return;
  showProfileSaveError("");
  if (input) input.disabled = true;
  try {
    const data = await uploadProfileAvatarFile(file);
    if (data?.user) {
      profile = data.user;
      applyProfileUI(profile);
      syncProfileEditForm(profile);
    }
  } catch (err) {
    showProfileSaveError(err.message || "頭像上傳失敗");
  } finally {
    if (input) {
      input.disabled = false;
      input.value = "";
    }
  }
}

function openProfileAvatarPicker() {
  const input = document.getElementById("profileAvatarInput");
  if (!input) return;
  showProfileSaveError("");
  input.click();
}

function openProfileSettings() {
  if (!isAuthenticated || !profile || userProfileModalClosing) return;
  closeProfileMenu();
  syncProfileEditForm(profile);
  showProfileSaveError("");
  const avatarInput = document.getElementById("profileAvatarInput");
  if (avatarInput) avatarInput.value = "";
  const modal = document.getElementById("userProfileModal");
  if (!modal) return;
  modal.classList.remove("closing");
  modal.classList.add("is-shown");
  modal.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
  requestAnimationFrame(() => {
    requestAnimationFrame(() => modal.classList.add("open"));
  });
  document.getElementById("profileEditDisplayName")?.focus();
}

function closeUserProfileModal() {
  const modal = document.getElementById("userProfileModal");
  if (!modal?.classList.contains("is-shown") || userProfileModalClosing) return;
  userProfileModalClosing = true;
  modal.classList.remove("open");
  modal.classList.add("closing");
  modal.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
  window.setTimeout(() => {
    modal.classList.remove("is-shown", "closing");
    userProfileModalClosing = false;
  }, PROFILE_MODAL_MS);
}

async function submitProfileEdit(e) {
  e.preventDefault();
  showProfileSaveError("");
  const display_name = (document.getElementById("profileEditDisplayName")?.value || "").trim();
  const bio = document.getElementById("profileEditBio")?.value || "";
  if (!display_name) {
    showProfileSaveError("請輸入顯示名稱");
    return;
  }
  try {
    const data = await fetchJson("/api/profile", {
      method: "PATCH",
      body: JSON.stringify({ display_name, bio }),
    });
    profile = data.user;
    applyProfileUI(profile);
    syncProfileEditForm(profile);
  } catch (err) {
    showProfileSaveError(err.message);
  }
}

function renderTwinMenu(twins, activeTwinId) {
  const list = document.getElementById("profileTwinList");
  if (!list) return;
  list.innerHTML = "";
  if (!twins.length) {
    list.innerHTML = '<p class="profile-twin-empty">尚無分身</p>';
    return;
  }
  for (const twin of twins) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "profile-twin-item" + (twin.is_active ? " active" : "");
    btn.dataset.twinId = twin.id;
    btn.dataset.preset = twin.preset || "custom";
    const presetLabel = TWIN_PRESET_LABELS[twin.preset] || twin.preset;
    btn.innerHTML = `
      <span class="profile-twin-dot" aria-hidden="true"></span>
      <span class="profile-twin-text">
        <span>${escapeHtml(twin.name)}</span>
        <span class="profile-twin-meta">${escapeHtml(presetLabel)}</span>
      </span>
    `;
    btn.addEventListener("click", () => activateTwin(twin.id));
    list.appendChild(btn);
  }
}

async function activateTwin(twinId) {
  try {
    const data = await fetchJson(`/api/twins/${twinId}/activate`, { method: "POST" });
    profile = data.user;
    applyProfileUI(profile);
    if (twinChatVisible) {
      updateTwinChatHeader();
      await loadTwinChat();
    }
  } catch (err) {
    alert(err.message);
  }
}

function showCreateTwinModalError(msg) {
  const el = document.getElementById("createTwinModalError");
  if (!el) return;
  if (!msg) {
    el.textContent = "";
    el.classList.add("hidden");
    return;
  }
  el.textContent = msg;
  el.classList.remove("hidden");
}

function openCreateTwinModal(opts = {}) {
  const { preferredPreset = "" } = opts;
  if (!isAuthenticated) {
    alert("請先登入後再建立數位分身");
    showAuthGate();
    return;
  }
  const modal = document.getElementById("createTwinModal");
  if (!modal) return;
  createTwinModalStep = 1;
  createTwinUploadFiles = [];
  createTwinProjectUploadFiles = [];
  showCreateTwinModalError("");
  updateTwinCreatePresetOptions(profile?.twins || [], {
    forceEnabledPreset: preferredPreset || "",
  });
  const nameEl = document.getElementById("createTwinModalName");
  if (preferredPreset) {
    const modalHost = document.getElementById("createTwinModalPresetButtons");
    let preferredInput = document.querySelector(
      `input[name="createTwinModalPreset"][value="${preferredPreset}"]`
    );
    if (!preferredInput && modalHost) {
      const label = document.createElement("label");
      label.className = "register-preset-option";
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "createTwinModalPreset";
      input.value = preferredPreset;
      const span = document.createElement("span");
      span.textContent = TWIN_PRESET_LABELS[preferredPreset] || preferredPreset;
      label.appendChild(input);
      label.appendChild(span);
      modalHost.prepend(label);
      preferredInput = input;
    }
    if (preferredInput instanceof HTMLInputElement) {
      preferredInput.checked = true;
    }
  }
  if (nameEl) nameEl.value = "";
  for (const id of STUDENT_FIELD_IDS) {
    const el = document.getElementById(id);
    if (el) el.value = "";
  }
  for (const id of COMPANY_FIELD_IDS) {
    const el = document.getElementById(id);
    if (el) el.value = "";
  }
  for (const id of LIFE_FIELD_IDS) {
    const el = document.getElementById(id);
    if (el) el.value = "";
  }
  for (const id of CUSTOM_FIELD_IDS) {
    const el = document.getElementById(id);
    if (el) el.value = "";
  }
  resetTwinStyleAnswers();
  document
    .querySelectorAll("#createTwinUploadTags .create-twin-upload-tag")
    .forEach((btn, idx) => btn.classList.toggle("active", idx === 0));
  document
    .querySelectorAll("#createTwinProjectUploadTags .create-twin-upload-tag")
    .forEach((btn, idx) => btn.classList.toggle("active", idx === 0));
  renderCreateTwinUploadList("createTwinUploadList", createTwinUploadFiles);
  renderCreateTwinUploadList("createTwinProjectUploadList", createTwinProjectUploadFiles);
  updateStudentGradeOptions();
  applyTwinNameRule(nameEl, getCreateTwinModalPresetValue());
  refreshCreateTwinModalLayout();
  modal.classList.add("open");
  const selectedPreset = getCreateTwinModalPresetValue();
  if (selectedPreset === "student") {
    document.getElementById("createTwinStudentEducation")?.focus();
  } else if (selectedPreset === "company") {
    document.getElementById("createTwinCompanyIndustry")?.focus();
  } else if (selectedPreset === "life") {
    document.getElementById("createTwinLifeStage")?.focus();
  } else if (selectedPreset === "custom") {
    document.getElementById("createTwinCustomRole")?.focus();
  } else {
    nameEl?.focus();
  }
}

function closeCreateTwinModal() {
  document.getElementById("createTwinModal")?.classList.remove("open");
}

async function createTwinWithPayload(payload) {
  const data = await fetchJson("/api/twins", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  profile = data.user;
  applyProfileUI(profile);
  await activateTwin(data.twin.id);
  return data;
}

async function submitCreateTwinModal(e) {
  e.preventDefault();
  showCreateTwinModalError("");
  const preset = getCreateTwinModalPresetValue();
  const isGuidedPreset =
    preset === "student" || preset === "company" || preset === "life" || preset === "custom";
  if (isGuidedPreset && createTwinModalStep < 4) {
    proceedCreateTwinModalStep();
    return;
  }
  let name = (document.getElementById("createTwinModalName")?.value || "").trim();
  let bio = "";
  let twin_context = "";
  if (!name && preset !== "custom") {
    name = TWIN_PRESET_LABELS[preset] || preset;
  }
  if (!name) {
    showCreateTwinModalError("請輸入分身名稱");
    return;
  }
  if (isGuidedPreset) {
    const styleAnswers = getTwinStyleAnswers();
    for (const key of TWIN_STYLE_QUESTION_IDS) {
      if (!styleAnswers[key]) {
        showCreateTwinModalError("請先完成思考與決策風格選擇");
        return;
      }
    }
    const styleRows = [
      `- 做決定時偏向：${styleAnswers.decision}`,
      `- 遇到問題優先考慮：${styleAnswers.priority}`,
      `- 說話風格：${styleAnswers.speech}`,
      `- 面對衝突時：${styleAnswers.conflict}`,
    ];
    if (preset === "student") {
      const education = (document.getElementById("createTwinStudentEducation")?.value || "").trim();
      const university = (document.getElementById("createTwinStudentUniversity")?.value || "").trim();
      const grade = (document.getElementById("createTwinStudentGrade")?.value || "").trim();
      const major = (document.getElementById("createTwinStudentMajor")?.value || "").trim();
      const skills = (document.getElementById("createTwinStudentSkills")?.value || "").trim();
      const intro = (document.getElementById("createTwinStudentIntro")?.value || "").trim();
      bio =
        intro ||
        `我是${STUDENT_EDUCATION_LABELS[education] || "學生"}${grade || ""}，擅長${
          skills || "整理重點與持續學習"
        }。`;
      const studentRows = [
        education ? `- 學歷：${STUDENT_EDUCATION_LABELS[education] || education}` : "",
        grade ? `- 年級：${grade}` : "",
        university ? `- 學校：${university}` : "",
        major ? `- 科系：${major}` : "",
        skills ? `- 個人專長：${skills}` : "",
        intro ? `- 個人簡介：${intro}` : "",
      ].filter(Boolean);
      if (studentRows.length) {
        const studentContext = [
          "學生分身基本資料：",
          ...studentRows,
          "",
          "思考與決策風格：",
          ...styleRows,
        ].join("\n");
        twin_context = [twin_context, studentContext].filter(Boolean).join("\n\n");
      }
    } else if (preset === "company") {
      const industry = (document.getElementById("createTwinCompanyIndustry")?.value || "").trim();
      const roleLevel = (document.getElementById("createTwinCompanyRoleLevel")?.value || "").trim();
      const companyName = (document.getElementById("createTwinCompanyName")?.value || "").trim();
      const department = (document.getElementById("createTwinCompanyDepartment")?.value || "").trim();
      const title = (document.getElementById("createTwinCompanyTitle")?.value || "").trim();
      const skills = (document.getElementById("createTwinCompanySkills")?.value || "").trim();
      const intro = (document.getElementById("createTwinCompanyIntro")?.value || "").trim();
      bio =
        intro ||
        `我是${COMPANY_INDUSTRY_LABELS[industry] || "公司"}領域的${
          COMPANY_ROLE_LABELS[roleLevel] || "工作者"
        }，擅長${skills || "跨部門協作與問題解決"}。`;
      const companyRows = [
        industry ? `- 產業別：${COMPANY_INDUSTRY_LABELS[industry] || industry}` : "",
        roleLevel ? `- 職位層級：${COMPANY_ROLE_LABELS[roleLevel] || roleLevel}` : "",
        companyName ? `- 公司名稱：${companyName}` : "",
        department ? `- 部門：${department}` : "",
        title ? `- 職稱：${title}` : "",
        skills ? `- 工作專長：${skills}` : "",
        intro ? `- 工作簡介：${intro}` : "",
      ].filter(Boolean);
      if (companyRows.length) {
        const companyContext = [
          "公司分身基本資料：",
          ...companyRows,
          "",
          "思考與決策風格：",
          ...styleRows,
        ].join("\n");
        twin_context = [twin_context, companyContext].filter(Boolean).join("\n\n");
      }
    } else if (preset === "life") {
      const stage = (document.getElementById("createTwinLifeStage")?.value || "").trim();
      const rhythm = (document.getElementById("createTwinLifeRhythm")?.value || "").trim();
      const city = (document.getElementById("createTwinLifeCity")?.value || "").trim();
      const interests = (document.getElementById("createTwinLifeInterests")?.value || "").trim();
      const goals = (document.getElementById("createTwinLifeGoals")?.value || "").trim();
      const stressRelief = (document.getElementById("createTwinLifeStressRelief")?.value || "").trim();
      const intro = (document.getElementById("createTwinLifeIntro")?.value || "").trim();
      bio =
        intro ||
        `我是${LIFE_STAGE_LABELS[stage] || "生活型"}，作息偏${LIFE_RHYTHM_LABELS[rhythm] || "彈性"}，近期目標是${
          goals || "讓生活更有節奏"
        }。`;
      const lifeRows = [
        stage ? `- 目前生活階段：${LIFE_STAGE_LABELS[stage] || stage}` : "",
        rhythm ? `- 作息節奏：${LIFE_RHYTHM_LABELS[rhythm] || rhythm}` : "",
        city ? `- 目前所在城市：${city}` : "",
        interests ? `- 興趣嗜好：${interests}` : "",
        goals ? `- 近期目標：${goals}` : "",
        stressRelief ? `- 紓壓方式：${stressRelief}` : "",
        intro ? `- 生活簡介：${intro}` : "",
      ].filter(Boolean);
      if (lifeRows.length) {
        const lifeContext = [
          "生活分身基本資料：",
          ...lifeRows,
          "",
          "思考與決策風格：",
          ...styleRows,
        ].join("\n");
        twin_context = [twin_context, lifeContext].filter(Boolean).join("\n\n");
      }
    } else if (preset === "custom") {
      const role = (document.getElementById("createTwinCustomRole")?.value || "").trim();
      const tone = (document.getElementById("createTwinCustomTone")?.value || "").trim();
      const domain = (document.getElementById("createTwinCustomDomain")?.value || "").trim();
      const boundaries = (document.getElementById("createTwinCustomBoundaries")?.value || "").trim();
      const goal = (document.getElementById("createTwinCustomGoal")?.value || "").trim();
      const keywords = (document.getElementById("createTwinCustomKeywords")?.value || "").trim();
      const intro = (document.getElementById("createTwinCustomIntro")?.value || "").trim();
      bio =
        intro ||
        `我是${CUSTOM_ROLE_LABELS[role] || "自訂"}分身，回覆語氣偏${
          CUSTOM_TONE_LABELS[tone] || "平衡清楚"
        }，主要協助${domain || "一般問題整理與決策建議"}。`;
      const customRows = [
        role ? `- 分身定位：${CUSTOM_ROLE_LABELS[role] || role}` : "",
        tone ? `- 回覆語氣：${CUSTOM_TONE_LABELS[tone] || tone}` : "",
        domain ? `- 主要使用情境：${domain}` : "",
        goal ? `- 希望達成目標：${goal}` : "",
        boundaries ? `- 希望避免內容：${boundaries}` : "",
        keywords ? `- 常用關鍵字：${keywords}` : "",
        intro ? `- 自訂簡介：${intro}` : "",
      ].filter(Boolean);
      if (customRows.length) {
        const customContext = [
          "自訂分身基本資料：",
          ...customRows,
          "",
          "思考與決策風格：",
          ...styleRows,
        ].join("\n");
        twin_context = [twin_context, customContext].filter(Boolean).join("\n\n");
      }
    }
    const tags = Array.from(
      document.querySelectorAll("#createTwinUploadTags .create-twin-upload-tag.active")
    )
      .map((n) => n.dataset.uploadTag || n.textContent.trim())
      .filter(Boolean);
    if (tags.length) {
      twin_context = [
        twin_context,
        `個人文字資料類型：${tags.join("、")}`,
      ]
        .filter(Boolean)
        .join("\n");
    }
    const projectTags = Array.from(
      document.querySelectorAll("#createTwinProjectUploadTags .create-twin-upload-tag.active")
    )
      .map((n) => n.dataset.uploadTag || n.textContent.trim())
      .filter(Boolean);
    if (projectTags.length) {
      twin_context = [
        twin_context,
        `專題背景資料類型：${projectTags.join("、")}`,
      ]
        .filter(Boolean)
        .join("\n");
    }
  }
  try {
    const created = await createTwinWithPayload({ name, preset, bio, twin_context });
    if (isGuidedPreset && created?.twin?.id) {
      await uploadCreateTwinFiles(created.twin.id, createTwinUploadFiles);
      await uploadCreateTwinFiles(created.twin.id, createTwinProjectUploadFiles);
    }
    closeCreateTwinModal();
  } catch (err) {
    showCreateTwinModalError(err.message || "建立分身失敗");
  }
}

function proceedCreateTwinModalStep() {
  const preset = getCreateTwinModalPresetValue();
  const isGuidedPreset =
    preset === "student" || preset === "company" || preset === "life" || preset === "custom";
  if (preset === "student" && createTwinModalStep === 1) {
    const education = (document.getElementById("createTwinStudentEducation")?.value || "").trim();
    const grade = (document.getElementById("createTwinStudentGrade")?.value || "").trim();
    if (!education) {
      showCreateTwinModalError("請先選擇學歷");
      document.getElementById("createTwinStudentEducation")?.focus();
      return;
    }
    if (!grade) {
      showCreateTwinModalError("請先選擇年級");
      document.getElementById("createTwinStudentGrade")?.focus();
      return;
    }
    showCreateTwinModalError("");
    goCreateTwinModalStep(2);
    return;
  }
  if (preset === "company" && createTwinModalStep === 1) {
    const industry = (document.getElementById("createTwinCompanyIndustry")?.value || "").trim();
    const roleLevel = (document.getElementById("createTwinCompanyRoleLevel")?.value || "").trim();
    if (!industry) {
      showCreateTwinModalError("請先選擇產業別");
      document.getElementById("createTwinCompanyIndustry")?.focus();
      return;
    }
    if (!roleLevel) {
      showCreateTwinModalError("請先選擇職位層級");
      document.getElementById("createTwinCompanyRoleLevel")?.focus();
      return;
    }
    showCreateTwinModalError("");
    goCreateTwinModalStep(2);
    return;
  }
  if (preset === "life" && createTwinModalStep === 1) {
    const stage = (document.getElementById("createTwinLifeStage")?.value || "").trim();
    const rhythm = (document.getElementById("createTwinLifeRhythm")?.value || "").trim();
    if (!stage) {
      showCreateTwinModalError("請先選擇目前生活階段");
      document.getElementById("createTwinLifeStage")?.focus();
      return;
    }
    if (!rhythm) {
      showCreateTwinModalError("請先選擇作息節奏");
      document.getElementById("createTwinLifeRhythm")?.focus();
      return;
    }
    showCreateTwinModalError("");
    goCreateTwinModalStep(2);
    return;
  }
  if (preset === "custom" && createTwinModalStep === 1) {
    const role = (document.getElementById("createTwinCustomRole")?.value || "").trim();
    const tone = (document.getElementById("createTwinCustomTone")?.value || "").trim();
    if (!role) {
      showCreateTwinModalError("請先選擇分身定位");
      document.getElementById("createTwinCustomRole")?.focus();
      return;
    }
    if (!tone) {
      showCreateTwinModalError("請先選擇回覆語氣");
      document.getElementById("createTwinCustomTone")?.focus();
      return;
    }
    showCreateTwinModalError("");
    goCreateTwinModalStep(2);
    return;
  }
  if (isGuidedPreset && createTwinModalStep === 2) {
    const styleAnswers = getTwinStyleAnswers();
    for (const key of TWIN_STYLE_QUESTION_IDS) {
      if (!styleAnswers[key]) {
        showCreateTwinModalError("請先完成思考與決策風格選擇");
        return;
      }
    }
    showCreateTwinModalError("");
    goCreateTwinModalStep(3);
    return;
  }
  if (isGuidedPreset && createTwinModalStep === 3) {
    showCreateTwinModalError("");
    goCreateTwinModalStep(4);
  }
}

function showAuthGate() {
  isAuthenticated = false;
  document.getElementById("authGate")?.classList.remove("hidden");
  document.getElementById("appRoot")?.classList.add("hidden");
  closeProfileMenu();
}

function showApp() {
  document.getElementById("authGate")?.classList.add("hidden");
  document.getElementById("appRoot")?.classList.remove("hidden");
}

function setAuthTab(tab) {
  const loginForm = document.getElementById("loginForm");
  const registerForm = document.getElementById("registerForm");
  const guestForm = document.getElementById("guestJoinForm");
  document.querySelectorAll(".auth-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.authTab === tab);
  });
  loginForm?.classList.toggle("hidden", tab !== "login");
  registerForm?.classList.toggle("hidden", tab !== "register");
  guestForm?.classList.add("hidden");
  document.querySelector(".auth-tabs")?.classList.remove("hidden");
  document.getElementById("btnShowGuestJoin")?.classList.add("hidden");
}

function showGuestJoinOnAuth() {
  setAuthTab("login");
  showAuthError("loginError", "訪客加入已停用，請先註冊或登入");
}

function showAuthError(elId, msg) {
  const el = document.getElementById(elId);
  if (!el) return;
  if (!msg) {
    el.textContent = "";
    el.classList.add("hidden");
    return;
  }
  el.textContent = msg;
  el.classList.remove("hidden");
}

async function checkAuth() {
  const data = await fetchJson("/api/auth/me");
  if (data.authenticated && data.user) {
    isAuthenticated = true;
    profile = data.user;
    applyProfileUI(profile);
    showApp();
    return true;
  }
  showAuthGate();
  return false;
}

async function submitLogin(e) {
  e.preventDefault();
  showAuthError("loginError", "");
  const login = document.getElementById("loginInput")?.value || "";
  const password = document.getElementById("loginPassword")?.value || "";
  try {
    const data = await fetchJson("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ login, password }),
    });
    isAuthenticated = true;
    profile = data.user;
    applyProfileUI(profile);
    showApp();
    await loadPersons();
    await loadSessions();
    startNotifyPolling();
  } catch (err) {
    showAuthError("loginError", err.message);
  }
}

async function submitRegister(e) {
  e.preventDefault();
  showAuthError("registerError", "");
  const email = document.getElementById("registerEmail")?.value || "";
  const username = document.getElementById("registerUsername")?.value || "";
  const password = document.getElementById("registerPassword")?.value || "";
  const initial_preset =
    document.querySelector('input[name="registerPreset"]:checked')?.value || "life";
  try {
    const data = await fetchJson("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({
        email,
        username,
        password,
        initial_preset,
      }),
    });
    isAuthenticated = true;
    profile = data.user;
    applyProfileUI(profile);
    showApp();
    await loadPersons();
    await loadSessions();
    startNotifyPolling();
    openCreateTwinModal({ preferredPreset: initial_preset });
  } catch (err) {
    showAuthError("registerError", err.message);
  }
}

function submitSocialAuth(provider) {
  const p = provider === "apple" ? "Apple" : "Google";
  alert(`${p} 登入功能準備中，下一步可接 OAuth 後端流程。`);
}

async function submitGuestJoinFromAuth(e) {
  e.preventDefault();
  showAuthError("guestJoinError", "訪客加入已停用，請先註冊或登入");
}

async function logout() {
  try {
    await fetchJson("/api/auth/logout", { method: "POST" });
  } catch {
    /* ignore */
  }
  isAuthenticated = false;
  profile = null;
  if (notifyPollTimer) clearInterval(notifyPollTimer);
  showAuthGate();
  setAuthTab("login");
}

function closeProfileMenu() {
  document.getElementById("profileMenu")?.classList.add("hidden");
}

function toggleProfileMenu() {
  if (!isAuthenticated) return;
  document.getElementById("profileMenu")?.classList.toggle("hidden");
}

async function loadPersons() {
  const data = await fetchJson("/api/persons");
  persons = data.persons || [];
  personCategories = data.categories || [];
  renderDiscoverFeed();
  renderModalPersons();
}

function openPersonProfileModal(p) {
  if (!p || profileModalClosing) return;
  profilePerson = p;
  const modal = document.getElementById("personProfileModal");
  if (!modal) return;
  const hero = document.getElementById("personProfileHero");
  if (hero) {
    hero.classList.remove("has-photo");
    hero.style.removeProperty("--hero-photo");
    const avatarUrl = p.avatar_url || personAvatarUrl(p.slug);
    if (avatarUrl && !String(avatarUrl).includes("gradient")) {
      hero.style.setProperty("--hero-photo", `url("${avatarUrl}")`);
      hero.classList.add("has-photo");
    }
  }

  const avatarHost = document.getElementById("personProfileAvatar");
  avatarHost.innerHTML = "";
  avatarHost.appendChild(
    avatarEl(p.name_zh, "avatar lg", p.slug, p.avatar_url)
  );
  document.getElementById("personProfileName").textContent = p.name_zh || "";
  document.getElementById("personProfileNameEn").textContent = p.name_en || "";

  const metaEl = document.getElementById("personProfileMeta");
  metaEl.innerHTML = `
    <span class="profile-meta-chip">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
      ${formatViews(p.doc_count)} 則資料
    </span>
  `;

  document.getElementById("personProfileBio").textContent = p.bio || "數位分身";

  const linksEl = document.getElementById("personProfileLinks");
  linksEl.innerHTML = "";
  const links = p.links && typeof p.links === "object" ? p.links : {};
  const entries = PERSON_LINK_ORDER.filter((key) => links[key]);
  if (!entries.length) {
    linksEl.innerHTML = '<p class="profile-links-empty">暫無外部連結</p>';
  } else {
    for (const key of entries) {
      const a = document.createElement("a");
      a.className = "profile-link-chip";
      a.href = links[key];
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.innerHTML = `${PERSON_LINK_ICONS[key] || ""}<span>${escapeHtml(personLinkLabel(p.slug, key))}</span>`;
      linksEl.appendChild(a);
    }
  }

  modal.classList.remove("closing");
  modal.classList.add("is-shown");
  modal.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
  requestAnimationFrame(() => {
    requestAnimationFrame(() => modal.classList.add("open"));
  });
}

function closePersonProfileModal() {
  const modal = document.getElementById("personProfileModal");
  if (!modal.classList.contains("is-shown") || profileModalClosing) return;
  profileModalClosing = true;
  modal.classList.remove("open");
  modal.classList.add("closing");
  modal.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";

  window.setTimeout(() => {
    modal.classList.remove("is-shown", "closing");
    profileModalClosing = false;
    profilePerson = null;
  }, PROFILE_MODAL_MS);
}

function openCreateModal(opts = {}) {
  const {
    slugs = [],
    topic = "",
    scrollToSlug = "",
    disableTopicRecommend = false,
  } = opts;
  topicRecommendDisabled = !!disableTopicRecommend;
  selectedSlugs = new Set(slugs);
  createRoomPendingFiles = [];
  if (typeof renderCreateRoomAttachPreview === "function") {
    renderCreateRoomAttachPreview();
  }
  const fileInput = document.getElementById("createRoomFiles");
  if (fileInput) fileInput.value = "";
  const topicInput = document.getElementById("roomTopic");
  if (topicInput) topicInput.value = topic;
  const personSearchInput = document.getElementById("modalPersonSearch");
  if (personSearchInput) personSearchInput.value = "";
  document.getElementById("createModal")?.classList.add("open");
  if (typeof setTopicRecommendPanelVisible === "function") {
    setTopicRecommendPanelVisible(!topicRecommendDisabled);
  }
  renderModalPersons();
  updateModalSelection();
  if (typeof resetCreateRoomSettings === "function") resetCreateRoomSettings();
  activeTopicRecommendTier = "high";
  const topicLen = (topicInput?.value || "").trim().length;
  if (!topicRecommendDisabled) {
    if (topicLen >= 2) scheduleTopicRecommendations();
    else if (typeof showTopicRecommendPlaceholder === "function")
      showTopicRecommendPlaceholder();
  }
  if (scrollToSlug) {
    requestAnimationFrame(() => {
      const row = document.querySelector(
        `.modal-person[data-slug="${scrollToSlug}"]`
      );
      row?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
  }
  if (topicInput && !topic) topicInput.focus();
}

function closeCreateModal() {
  document.getElementById("createModal")?.classList.remove("open");
  topicRecommendDisabled = false;
  if (typeof setTopicRecommendPanelVisible === "function") {
    setTopicRecommendPanelVisible(false);
  }
}

