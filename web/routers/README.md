# routers｜HTTP 請求入口

接收瀏覽器請求、驗證參數、呼叫功能並回傳結果。由 app.py 註冊路由。

| 檔案／資料夾 | 負責的內容 |
| --- | --- |
| `pages.py` | 首頁 / 與實驗室 /lab。 |
| `auth.py` | 登入狀態、註冊、登入與登出。 |
| `profile.py` | 個人資料、頭像上傳與讀取。 |
| `twins.py` | 建立、列出、切換分身與上傳背景資料。 |
| `twin_chat.py` | 個人分身私聊訊息與附件。 |
| `person_chat.py` | 名人私聊清單、訊息與刪除。 |
| `persons.py` | 人物分類、清單與主題推薦。 |
| `sessions.py` | 建立、加入、預覽、讀取、置頂、刪除討論室與上傳參考資料。 |
| `discussion.py` | 討論進度、下一輪與使用者插話。 |
| `insights.py` | 心智圖、立場分析與快取。 |
| `notifications.py` | 加入通知、未讀數量與已讀操作。 |
| `media.py` | 彙整各聊天來源的附件。 |
| `query.py` | RAG 檢索與來源回傳。 |

`__init__.py` 是 Python 套件標記與簡短說明。
