# TwinMind｜分身有術

個人數位分身、名人知識庫與多人議題討論平台。
後端為 Python / FastAPI，前端為 HTML / CSS / JavaScript，資料庫為 PostgreSQL。

## 先看這裡

- [Web 資料夾導覽](web/README.md)：每個資料夾的職責。
- [完整架構與閱讀順序](docs/ARCHITECTURE.md)：功能對照、流程和新舊檔案位置。
- 每個 web 功能資料夾都有自己的 README，說明裡面的檔案。

## 啟動現有本機環境

在專案根目錄執行：

```bash
./venv/bin/uvicorn web.app:app --reload --host 127.0.0.1 --port 8000
```

網站：<http://127.0.0.1:8000>；API 文件：<http://127.0.0.1:8000/docs>。
根目錄仍保留 `web/app.py`，原本指令不變。

`.env` 保留在專案根目錄，不要提交真實金鑰。
換電腦時，還需要 Python 套件、PostgreSQL、資料表、上傳檔案與 embedding 模型。
資料庫設定目前仍在 `rag/config.py` 等既有模組，尚未全面集中為環境變數。

## 測試

```bash
./venv/bin/python -B -m unittest discover -s tests -v
```

使用替身檢查 API 與搬移後的模組、路徑，不連真實資料庫、不呼叫 OpenAI。

## 版本控制

先用 `git status` 和 `git diff` 檢查修改，再選擇這次要提交的檔案。
本機修改必須 commit 並 push 後才會出現在 GitHub，並不會自動同步。
