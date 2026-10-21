-- 範例資料：測試爬蟲 → documents → chunks 流程
-- 執行前請先跑過 schema.sql

BEGIN;

INSERT INTO documents (person_id, source_url, title, source_type, raw_content, content_hash)
VALUES (
    (SELECT id FROM persons WHERE slug = 'elon_musk'),
    'https://example.com/elon-sample-1',
    '範例：馬斯克談創新（測試用）',
    'interview',
    '我認為創新需要承擔風險，失敗是學習的一部分。我們必須把資源集中在最重要的事情上，並且快速迭代。',
    'hash_elon_sample_1'
)
ON CONFLICT (person_id, source_url) DO NOTHING;

INSERT INTO chunks (document_id, person_id, chunk_index, content, metadata)
SELECT
    d.id,
    d.person_id,
    0,
    d.raw_content,
    jsonb_build_object('title', d.title, 'source_url', d.source_url)
FROM documents d
WHERE d.source_url = 'https://example.com/elon-sample-1'
ON CONFLICT (document_id, chunk_index) DO NOTHING;

COMMIT;
