# repositories｜共用資料庫存取

帳號與討論室的 PostgreSQL 操作；不註冊 HTTP 路由。

| 檔案／資料夾 | 負責的內容 |
| --- | --- |
| `user_store.py` | 帳號、登入 session、個人資料、分身設定與預設角色。 |
| `chat_store.py` | 討論室、參與者、加入碼、訊息、通知、置頂及分析資料。 |

`__init__.py` 是 Python 套件標記與簡短說明。

目前私聊模組仍保留自己的建表與訊息 SQL，個人知識庫也有專屬 SQL；本次以資料夾分類與匯入整理為主，尚未把所有 SQL 集中到 repositories。
