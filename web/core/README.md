# core｜共用基礎

網站設定、啟動、驗證與執行資源，供各功能共用。

| 檔案／資料夾 | 負責的內容 |
| --- | --- |
| `settings.py` | 讀取專案根目錄 .env，設定靜態檔、頭像、Cookie 與環境參數。 |
| `lifecycle.py` | 啟動時執行既有建表／補欄位流程，以及背景模型暖機。 |
| `dependencies.py` | 登入檢查、Cookie 操作、聊天室存取檢查與共用參數處理。 |
| `session_auth.py` | 密碼雜湊與驗證、加入碼和隨機 token。 |
| `runtime.py` | 共用執行緒池與日誌。 |
| `rag_backend.py` | 網頁連接專案根目錄 rag/ 的單一相容入口；不在此執行查詢或生成。 |

`__init__.py` 是 Python 套件標記與簡短說明。
