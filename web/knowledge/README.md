# knowledge｜文件與知識庫

將文字或檔案整理成可檢索資料，並讀取個人或討論室的相關片段。

| 檔案／資料夾 | 負責的內容 |
| --- | --- |
| `file_extract.py` | 從文字、PDF、DOCX、PPTX 檔案擷取文字與預覽。 |
| `user_rag.py` | 個人資料切段、向量化、聊天補匯與檢索。 |
| `session_context.py` | 討論室附件保存、匯入 RAG 與整理背景摘要。 |
| `person_profile_seed.py` | 把 data/person_profiles.py 的人物資料寫入資料庫。 |

`__init__.py` 是 Python 套件標記與簡短說明。

若需要手動匯入人物資料，請從專案根目錄執行 `./venv/bin/python -m web.knowledge.person_profile_seed`。此命令會寫入資料庫。
