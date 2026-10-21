-- 名人頭像欄位
ALTER TABLE persons ADD COLUMN IF NOT EXISTS avatar_url TEXT;
ALTER TABLE persons ADD COLUMN IF NOT EXISTS avatar_source TEXT;  -- wikipedia_en, wikipedia_zh, manual
