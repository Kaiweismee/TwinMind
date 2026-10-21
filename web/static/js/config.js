/* js/config.js */
const API = "";
const DT_ROOMS_KEY = "dt_rooms";

let profile = null;
let isAuthenticated = false;
let persons = [];
let personCategories = [];
let activeCategoryId = null;
let sessions = [];
let personChatThreads = [];
let currentSessionId = null;
let currentSession = null;
let selectedSlugs = new Set();
let globalSearchQuery = "";
let topicRecommendations = [];
let topicRecommendTimer = null;
let topicRecommendFetchId = 0;
let activeTopicRecommendTier = "high";
let topicRecommendDisabled = false;
const TOPIC_RECOMMEND_MIN_LOAD_MS = 5000;
let createRoomPendingFiles = [];
const CREATE_ROOM_MAX_FILES = 6;

const SCENES = [
  {
    title: "AI 產業圓桌",
    topic: "AI 產業圓桌：人才、晶片與平台競爭",
    subtitle: "AI 人才與產業鏈",
    slugs: ["jensen_huang", "andrew_ng", "sam_altman", "elon_musk"],
    image: "/static/images/scenes/ai-roundtable.png",
    gradient: "linear-gradient(160deg, #1e3a5f 0%, #4c1d95 50%, #0f172a 100%)",
  },
  {
    title: "產品策略會議",
    topic: "產品策略會議：從 0 到 1 與平台擴張",
    subtitle: "產品、平台與使用者體驗",
    slugs: ["steve_jobs", "tim_cook", "mark_zuckerberg", "bill_gates"],
    image: "/static/images/scenes/product strategy meeting.png",
    gradient: "linear-gradient(160deg, #374151 0%, #1f2937 60%, #111827 100%)",
  },
  {
    title: "投資與風險圓桌",
    topic: "投資與風險圓桌：AI 浪潮下的資產配置",
    subtitle: "投資決策與風險管理",
    slugs: ["warren_buffett", "ray_dalio", "bill_gates", "elon_musk"],
    image: "/static/images/scenes/Investment and Risk.png",
    gradient: "linear-gradient(160deg, #78350f 0%, #92400e 50%, #451a03 100%)",
  },
  {
    title: "文學倫理討論",
    topic: "文學倫理討論：古今思想家的價值觀交鋒",
    subtitle: "東西方哲學與人文精神",
    slugs: ["confucius", "aristotle", "leonardo_da_vinci", "abraham_lincoln"],
    image: "/static/images/scenes/Literary Ethics .png",
    gradient: "linear-gradient(160deg, #44403c 0%, #78716c 40%, #292524 100%)",
  },
  {
    title: "帝王將相兵棋推演",
    topic: "帝王將相兵棋推演：亂世中如何做決策",
    subtitle: "戰略、談判與領導抉擇",
    slugs: ["sun_tzu", "zhuge_liang", "napoleon_bonaparte", "winston_churchill"],
    image: "/static/images/scenes/War Game Simulation.png",
    gradient: "linear-gradient(160deg, #111827 0%, #7f1d1d 50%, #1f2937 100%)",
  },
  {
    title: "跨世代教育改革會議",
    topic: "跨世代教育改革會議：AI 時代的學習能力藍圖",
    subtitle: "教育理論 × 實作創新",
    slugs: ["john_dewey", "maria_montessori", "ken_robinson", "sal_khan"],
    image: "/static/images/scenes/Revolutionary Education Reform.png",
    gradient: "linear-gradient(160deg, #064e3b 0%, #0f766e 50%, #1e293b 100%)",
  },
  {
    title: "科學與工程未來論壇",
    topic: "科學與工程未來論壇：基礎研究到產業落地",
    subtitle: "科學洞見 × 工程實踐",
    slugs: ["albert_einstein", "marie_curie", "nikola_tesla", "linus_torvalds"],
    image: "/static/images/scenes/Science and Engineering Future Forum.png",
    gradient: "linear-gradient(160deg, #0f172a 0%, #1d4ed8 48%, #312e81 100%)",
  },
];

const PERSON_LINK_ORDER = [
  "wikipedia_zh",
  "wikipedia_en",
  "twitter",
  "instagram",
  "facebook",
  "linkedin",
  "youtube",
  "company",
];

const PERSON_LINK_LABELS = {
  wikipedia_zh: "維基百科",
  wikipedia_en: "Wikipedia",
  twitter: "X",
  instagram: "Instagram",
  facebook: "Facebook",
  linkedin: "LinkedIn",
  youtube: "YouTube",
  company: "官網",
};

const PERSON_LINK_LABEL_OVERRIDES = {
  jensen_huang: {
    company: "NVIDIA",
  },
};

function personLinkLabel(slug, key) {
  return PERSON_LINK_LABEL_OVERRIDES[slug]?.[key] || PERSON_LINK_LABELS[key] || key;
}

const PERSON_LINK_ICONS = {
  wikipedia_zh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>',
  wikipedia_en: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M8 8c1 3 2 5 4 8M16 8c-1 3-2 5-4 8M7 12h10"/></svg>',
  twitter: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>',
  instagram: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none"/></svg>',
  facebook: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M24 12.073C24 5.405 18.627 0 12 0S0 5.405 0 12.073C0 18.1 4.388 23.094 10.125 24v-8.437H7.078v-3.49h3.047V9.413c0-3.025 1.792-4.697 4.533-4.697 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.49h-2.796V24C19.612 23.094 24 18.1 24 12.073z"/></svg>',
  linkedin: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 114.126 0 2.063 2.063 0 01-2.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>',
  youtube: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 00-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 00.502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 002.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 002.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>',
  company: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 21h18M5 21V7l8-4v18M19 21V11l-6-3"/><path d="M9 9v.01M9 12v.01M9 15v.01M9 18v.01"/></svg>',
};

let profilePerson = null;
let profileModalClosing = false;
let userProfileModalClosing = false;

const PROFILE_MODAL_MS = 320;

const CATEGORY_TILE_GRADIENTS = {
  tech: "linear-gradient(160deg, #1e3a5f 0%, #4c1d95 50%, #0f172a 100%)",
  education: "linear-gradient(160deg, #065f46 0%, #047857 50%, #134e4a 100%)",
  business: "linear-gradient(160deg, #78350f 0%, #92400e 50%, #451a03 100%)",
  historical: "linear-gradient(160deg, #374151 0%, #1f2937 60%, #111827 100%)",
};

const AVATAR_GRADIENTS = [
  ["#6366f1", "#8b5cf6"],
  ["#ec4899", "#f43f5e"],
  ["#0ea5e9", "#06b6d4"],
  ["#f59e0b", "#ef4444"],
  ["#10b981", "#3b82f6"],
  ["#a855f7", "#6366f1"],
];

