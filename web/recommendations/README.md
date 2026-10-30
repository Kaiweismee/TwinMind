# recommendations｜人物推薦

判斷人物與討論主題的契合度、排序及對應參與設定。

| 檔案／資料夾 | 負責的內容 |
| --- | --- |
| `topic_fit.py` | 關鍵字評分、契合等級、辯論輪數與評分方式選擇。 |
| `topic_fit_semantic.py` | 知識庫語意相似度與關鍵字混合評分。 |
| `topic_fit_llm.py` | 用人物簡介與檢索資料，交給 AI 批次評分、排序和快取。 |

`__init__.py` 是 Python 套件標記與簡短說明。
