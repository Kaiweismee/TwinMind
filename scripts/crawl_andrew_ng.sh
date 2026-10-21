#!/usr/bin/env bash
# 吳恩達（andrew_ng）完整爬蟲 + 向量化
set -euo pipefail
cd "$(dirname "$0")/.."
PY=./venv/bin/python
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY 2>/dev/null || true

echo "=== person_auto 全流程 ==="
"$PY" crawl/person_auto.py \
  --name-zh "吳恩達" \
  --name-en "Andrew Ng" \
  --company "Stanford DeepLearning.AI Coursera" \
  --slug andrew_ng \
  --wiki-pages "zh:吴恩达,en:Andrew_Ng,en:Coursera" \
  --extra-queries "Andrew Ng agentic AI,吳恩達 生成式 AI" \
  --youtube "0jspaMLxBig:Lex #73,jGwO-UgTSX4:What is ML,MniNHtKg270:State of AI" \
  --youtube-max 10 \
  --skip-embed-hint

echo ""
echo "=== 補強：維基多篇 + 演講 + 訪談 ==="
"$PY" crawl/wikipedia_more.py --person andrew_ng
"$PY" crawl/speech_fetch.py --person andrew_ng
"$PY" crawl/interview_fetch.py --person andrew_ng
"$PY" crawl/news_rss.py --person andrew_ng

echo ""
echo "=== 向量化 ==="
"$PY" rag/embed_chunks.py --no-index

echo ""
echo "完成。測試："
echo '  ./venv/bin/python rag/query.py "吳恩達怎麼看生成式 AI" --person andrew_ng'
