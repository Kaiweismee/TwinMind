#!/bin/bash
# PostgreSQL 16 → 17 遷移 + 啟用 pgvector
# 用法：cd ~/Desktop/digital_twin_project && bash scripts/migrate_to_pg17.sh

set -e

PG16="/opt/homebrew/opt/postgresql@16/bin"
PG17="/opt/homebrew/opt/postgresql@17/bin"
BACKUP="$HOME/digital_twin_backup.sql"
DB="digital_twin"

echo "=== 1. 备份 digital_twin (PostgreSQL 16) ==="
if [ ! -x "$PG16/pg_dump" ]; then
  echo "找不到 PostgreSQL 16，请确认已安装 postgresql@16"
  exit 1
fi
"$PG16/pg_dump" "$DB" > "$BACKUP"
echo "✓ 已备份到 $BACKUP"
ls -lh "$BACKUP"

echo ""
echo "=== 2. 安装并启动 PostgreSQL 17 ==="
brew install postgresql@17
brew services stop postgresql@16 || true
brew services start postgresql@17
sleep 2

echo ""
echo "=== 3. 建立资料库并还原 ==="
if "$PG17/psql" -lqt | cut -d \| -f 1 | grep -qw "$DB"; then
  echo "资料库 $DB 已存在，先删除再还原…"
  "$PG17/dropdb" "$DB" || true
fi
"$PG17/createdb" "$DB"
"$PG17/psql" "$DB" < "$BACKUP"
echo "✓ 还原完成"

echo ""
echo "=== 4. 启用 pgvector ==="
"$PG17/psql" "$DB" -c "CREATE EXTENSION IF NOT EXISTS vector;"
"$PG17/psql" "$DB" -c "\\dx vector"

echo ""
echo "=== 5. 专案内设定向量栏位 ==="
cd "$(dirname "$0")/.."
./venv/bin/python db/setup_pgvector.py

echo ""
echo "=== 完成 ==="
echo "请改用 PostgreSQL 17 的 psql："
echo "  $PG17/psql $DB"
echo ""
echo "下一步（语意向量，需网络下载模型）："
echo "  unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy"
echo "  ./venv/bin/python rag/embed_chunks.py --no-index"
echo ""
echo "或继续用 TF-IDF（不需下载模型）："
echo "  ./venv/bin/python rag/embedder_tfidf.py"
echo "  EMBEDDING_BACKEND=tfidf ./venv/bin/python rag/query.py \"问题\" --person jensen_huang"
