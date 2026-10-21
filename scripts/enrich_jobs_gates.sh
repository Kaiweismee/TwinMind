#!/usr/bin/env bash
# 補抓賈伯斯／蓋茲：維基 + YouTube 演講字幕 + 訪談 YouTube
# 用法：cd ~/Desktop/digital_twin_project && bash scripts/enrich_jobs_gates.sh

set -euo pipefail
cd "$(dirname "$0")/.."
PY=./venv/bin/python

unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY 2>/dev/null || true

echo "=== 賈伯斯 ==="
"$PY" crawl/wikipedia_more.py --person steve_jobs
"$PY" crawl/speech_fetch.py --person steve_jobs
"$PY" crawl/interview_fetch.py --person steve_jobs

echo ""
echo "=== 蓋茲 ==="
"$PY" crawl/wikipedia_more.py --person bill_gates
"$PY" crawl/speech_fetch.py --person bill_gates
"$PY" crawl/interview_fetch.py --person bill_gates

echo ""
echo "=== 向量化（新 chunks）==="
"$PY" rag/embed_chunks.py --no-index

echo ""
echo "=== 完成。可檢查：==="
echo "  SELECT p.slug, d.source_type, COUNT(*) FROM documents d"
echo "  JOIN persons p ON p.id=d.person_id"
echo "  WHERE p.slug IN ('steve_jobs','bill_gates') GROUP BY 1,2;"
