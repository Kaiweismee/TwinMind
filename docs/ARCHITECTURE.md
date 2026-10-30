# TwinMind 程式架構與閱讀順序

網頁功能依責任分成資料夾。根目錄只保留啟動入口、套件標記與這份說明。
Python 自動產生的 `__pycache__/` 和 macOS 的 `.DS_Store` 不屬於功能程式。

```text
web/
├── app.py              # 保留原啟動入口 web.app:app
├── __init__.py         # Python 套件標記
├── README.md           # 資料夾導覽
├── core/               # 設定、啟動、驗證與共用資源
├── routers/            # HTTP API 入口
├── schemas/            # 請求欄位與驗證規則
├── services/           # 串接功能的處理流程
├── conversations/      # 對話、提示詞、討論與分析
├── repositories/       # 帳號與討論室資料庫存取
├── knowledge/          # 文件處理與知識庫
├── recommendations/    # 人物推薦與契合度
├── static/             # 網頁、JavaScript、CSS、圖片
└── archive/            # 舊備份，不參與執行
```

## 每個資料夾做什麼

| 資料夾 | 負責的事 |
| --- | --- |
| [core](../web/core/README.md) | 共用基礎 |
| [routers](../web/routers/README.md) | HTTP 請求入口 |
| [schemas](../web/schemas/README.md) | API 資料格式 |
| [services](../web/services/README.md) | 應用流程 |
| [conversations](../web/conversations/README.md) | 對話與討論 |
| [repositories](../web/repositories/README.md) | 共用資料庫存取 |
| [knowledge](../web/knowledge/README.md) | 文件與知識庫 |
| [recommendations](../web/recommendations/README.md) | 人物推薦 |
| [static](../web/static/README.md) | 前端畫面與素材 |
| [archive](../web/archive/README.md) | 歷史備份 |

## 用一條流程理解分工

使用者按傳送 → `static/js/` 送出請求 → `routers/` 接收 →
`schemas/` 與 `core/dependencies.py` 驗證 → `services/` 串接流程 →
`conversations/`、`knowledge/`、`repositories/` 完成處理 → 回傳給前端顯示。

實際上部分較短的路由會直接呼叫功能模組，不一定每次都經過 services。

同名檔案要看資料夾：`routers/person_chat.py` 是 HTTP 入口，
`conversations/person_chat.py` 是名人對話處理。
`services/recommendations.py` 處理執行與逾時，`recommendations/` 處理評分方法。

每個功能資料夾都有 README，列出其中所有主要檔案的用途。
以下接著說明閱讀順序、檔案搬移與驗證方式。

## 啟動方式

在專案根目錄執行，指令維持不變：

```bash
./venv/bin/uvicorn web.app:app --reload --host 127.0.0.1 --port 8000
```

若程式在搬移過程中觸發自動重新載入而暫時報錯，搬移完成後重新執行上述指令即可。

## 匯入規則

請使用完整套件路徑，例如：

```python
from web.repositories import chat_store
from web.conversations import discussion
from web.schemas.requests import SendMessageRequest
```

不要再使用 `import chat_store` 等依賴搜尋路徑的寫法。
專案根目錄的 rag/ 尚有命令列匯入相容需求，網頁統一透過 `core/rag_backend.py` 存取。

## 建議閱讀順序

1. `web/app.py`：先看有哪些路由被掛進網站。
2. `web/static/js/session.js` 的 `requestNextTurn()`：瀏覽器如何要求下一輪。
3. `web/routers/discussion.py` 的 `api_next_turn()`：接收請求與檢查存取權。
4. `web/schemas/requests.py` 的 `TurnRequest`：請求有哪些欄位。
5. `web/services/turns.py` 的 `_run_single_turn()`：準備聊天室與個人背景。
6. `web/conversations/discussion.py` 的 `run_next_turn()`：決定發言者、提示詞與引用。
7. `rag/search.py` 與 `web/repositories/chat_store.py`：檢索知識與儲存發言。

每個函式先看輸入、主要動作和回傳值，再深入實作。

## 想改功能，去哪裡

| 要改的功能 | 先看 |
| --- | --- |
| 網頁外觀 | `web/static/css/` 與 `web/static/index.html` |
| 點擊後的操作 | `web/static/js/` |
| 登入／註冊 | `web/routers/auth.py`、`web/repositories/user_store.py` |
| 個人分身回答 | `web/conversations/twin_chat.py` |
| 名人私聊回答 | `web/conversations/person_chat.py` |
| 辯論順序、輪數、引用 | `web/conversations/discussion.py` |
| 插話與逾時備援 | `web/services/messages.py` |
| 心智圖與立場分析內容 | `web/conversations/discussion_insights.py` |
| 心智圖如何畫出來 | `web/static/js/insights.js` |
| 人物推薦評分 | `web/recommendations/` |
| 個人知識／文件解析 | `web/knowledge/` |
| 網頁環境與資源路徑 | `web/core/settings.py` |

## 舊檔案搬去哪裡

下表以專案根目錄為起點；原先的檔案已搬移，請使用新路徑。

| 舊位置 | 新位置 |
| --- | --- |
| `web/settings.py` | `web/core/settings.py` |
| `web/dependencies.py` | `web/core/dependencies.py` |
| `web/runtime.py` | `web/core/runtime.py` |
| `web/lifecycle.py` | `web/core/lifecycle.py` |
| `web/session_auth.py` | `web/core/session_auth.py` |
| `web/chat_store.py` | `web/repositories/chat_store.py` |
| `web/user_store.py` | `web/repositories/user_store.py` |
| `web/discussion.py` | `web/conversations/discussion.py` |
| `web/discussion_insights.py` | `web/conversations/discussion_insights.py` |
| `web/person_chat.py` | `web/conversations/person_chat.py` |
| `web/twin_chat.py` | `web/conversations/twin_chat.py` |
| `web/file_extract.py` | `web/knowledge/file_extract.py` |
| `web/user_rag.py` | `web/knowledge/user_rag.py` |
| `web/session_context.py` | `web/knowledge/session_context.py` |
| `web/person_profile_seed.py` | `web/knowledge/person_profile_seed.py` |
| `web/topic_fit.py` | `web/recommendations/topic_fit.py` |
| `web/topic_fit_semantic.py` | `web/recommendations/topic_fit_semantic.py` |
| `web/topic_fit_llm.py` | `web/recommendations/topic_fit_llm.py` |
| `web/schemas.py` | `web/schemas/requests.py` |
| `web/discussion_insights.py.backup_20260526_2241` | `web/archive/discussion_insights.py.backup_20260526_2241` |

原本 `web/legacy.py` 已移除：web 模組改為完整套件匯入，對既有 rag/ 的銜接集中在 `web/core/rag_backend.py`。

## 資料與功能的界線

- PostgreSQL 保存帳號、知識文字、向量、訊息與分析結果。
- `data/twin_uploads/` 保存實體附件，`data/profile_avatars/` 保存使用者頭像。
- `.env` 仍在專案根目錄；搬移不改動金鑰。
- 個人記憶是 RAG 資料匯入與檢索，並非重新訓練模型。
- 個人分身與名人私聊模組仍有自己的 SQL，知識庫也有專屬 SQL；這次沒有宣稱所有資料存取已集中。
- `agents/crew_discuss.py` 是另一套 CrewAI 命令列流程，網站討論使用 `web/conversations/discussion.py`。
- 前端 JS 共用全域狀態，HTML 的載入順序保留；本次不改畫面和前端行為。
- `db/` SQL 與啟動時的 `ensure_*_schema()` 共同定義目前資料表；本次未新增資料庫欄位。

## 驗證與版本控制

```bash
./venv/bin/python -B -m unittest discover -s tests -v
```

測試使用替身，包含 API 格式、登入限制、靜態頁面、模組匯入、上傳路徑、個人記憶、推薦與分析快取。
不連真實 PostgreSQL，不呼叫 OpenAI；仍須另做實際環境的整合驗證。

`tests/fixtures/web_openapi.json` 保留原有 42 個 API 操作的規格。
刻意改 API 時，先審查差異，再更新測試基準。

檔案搬移尚未自動提交或推送到 GitHub。確認後可把整次結構調整作為獨立 commit，
避免和新增功能混在一起。不要同時在新舊檔案各保留一份正在使用的實作。
