# Web 資料夾導覽

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
| [core](core/README.md) | 共用基礎 |
| [routers](routers/README.md) | HTTP 請求入口 |
| [schemas](schemas/README.md) | API 資料格式 |
| [services](services/README.md) | 應用流程 |
| [conversations](conversations/README.md) | 對話與討論 |
| [repositories](repositories/README.md) | 共用資料庫存取 |
| [knowledge](knowledge/README.md) | 文件與知識庫 |
| [recommendations](recommendations/README.md) | 人物推薦 |
| [static](static/README.md) | 前端畫面與素材 |
| [archive](archive/README.md) | 歷史備份 |

## 用一條流程理解分工

使用者按傳送 → `static/js/` 送出請求 → `routers/` 接收 →
`schemas/` 與 `core/dependencies.py` 驗證 → `services/` 串接流程 →
`conversations/`、`knowledge/`、`repositories/` 完成處理 → 回傳給前端顯示。

實際上部分較短的路由會直接呼叫功能模組，不一定每次都經過 services。

同名檔案要看資料夾：`routers/person_chat.py` 是 HTTP 入口，
`conversations/person_chat.py` 是名人對話處理。
`services/recommendations.py` 處理執行與逾時，`recommendations/` 處理評分方法。

每個功能資料夾都有 README，列出其中所有主要檔案的用途。
完整閱讀順序與搬移對照在 [架構文件](../docs/ARCHITECTURE.md)。

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
