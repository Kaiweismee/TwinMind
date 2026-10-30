# services｜應用流程

串接使用者資料、知識庫、對話與回傳結果；回答「這件事情依序怎麼完成」。

| 檔案／資料夾 | 負責的內容 |
| --- | --- |
| `ai.py` | 檢查金鑰、建立 OpenAI 用戶端與選擇模型。 |
| `knowledge.py` | 登入後確保個人知識庫存在，必要時補匯聊天資料。 |
| `recommendations.py` | 執行人物推薦並處理等待、逾時和錯誤。 |
| `turns.py` | 準備討論室與個人背景、推進一輪並回傳下一位發言者。 |
| `messages.py` | 儲存插話、選擇回覆對象、安排回答與處理逾時備援。 |

`__init__.py` 是 Python 套件標記與簡短說明。

`services` 決定何時呼叫哪些功能；`conversations` 處理具體角色對話；`recommendations` 計算人物契合度；`knowledge` 建立與查詢知識資料。
