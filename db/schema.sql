-- 數位分身畢專：digital_twin 資料庫結構
-- 在 pgAdmin 對 digital_twin 執行，或：psql digital_twin -f db/schema.sql

BEGIN;

-- ---------------------------------------------------------------------------
-- 名人
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS persons (
    id          SERIAL PRIMARY KEY,
    slug        TEXT NOT NULL UNIQUE,          -- 程式用識別，例如 elon_musk
    name_zh     TEXT NOT NULL,                 -- 黃仁勳
    name_en     TEXT NOT NULL,                 -- Jensen Huang
    display_name_zh TEXT,                      -- UI 顯示別名
    display_name_en TEXT,                      -- UI 顯示英文別名
    bio         TEXT,                          -- 簡短介紹（可選）
    display_bio TEXT,                          -- 將姓名換成顯示別名的簡介
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 爬蟲來源文件（一篇網頁 / 一篇報導 / 一份演講稿）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id              SERIAL PRIMARY KEY,
    person_id       INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    source_url      TEXT NOT NULL,
    title           TEXT,
    author          TEXT,
    source_type     TEXT NOT NULL DEFAULT 'web',  -- web, interview, speech, news, wiki, other
    language        TEXT NOT NULL DEFAULT 'zh',
    raw_content     TEXT NOT NULL,                -- 爬下來的原文
    content_hash    TEXT,                         -- 去重用（同一 URL 或內容 hash）
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (person_id, source_url)
);

CREATE INDEX IF NOT EXISTS idx_documents_person_id ON documents(person_id);
CREATE INDEX IF NOT EXISTS idx_documents_scraped_at ON documents(scraped_at DESC);

-- ---------------------------------------------------------------------------
-- RAG 分塊（一篇文件切成多段）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chunks (
    id              SERIAL PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    person_id       INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
    chunk_index     INTEGER NOT NULL,             -- 同文件內第幾塊，從 0 開始
    content         TEXT NOT NULL,
    token_count     INTEGER,                      -- 可選：記錄大概 token 數
    metadata        JSONB NOT NULL DEFAULT '{}',  -- 例如 {"section": "引言"}
    -- embedding 欄位在安裝 pgvector 後用 db/schema_pgvector.sql 加入
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_chunks_person_id ON chunks(person_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document_id ON chunks(document_id);

-- 全文檢索（尚未有向量時可先靠關鍵字，可選）
CREATE INDEX IF NOT EXISTS idx_chunks_content_fts
    ON chunks USING GIN (to_tsvector('simple', content));

-- ---------------------------------------------------------------------------
-- CrewAI 討論：一場對話
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_sessions (
    id          SERIAL PRIMARY KEY,
    topic       TEXT NOT NULL,                    -- 討論題目
    summary     TEXT,                             -- 結束後可寫摘要
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at    TIMESTAMPTZ
);

-- ---------------------------------------------------------------------------
-- 每一輪發言
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_messages (
    id                  SERIAL PRIMARY KEY,
    session_id          INTEGER NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    person_id           INTEGER REFERENCES persons(id) ON DELETE SET NULL,  -- NULL = 主持人/系統
    role                TEXT NOT NULL,          -- musk, jensen, moderator, system
    content             TEXT NOT NULL,
    retrieved_chunk_ids INTEGER[] DEFAULT '{}',   -- 本輪 RAG 引用了哪些 chunk
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chat_messages_role_check
        CHECK (role IN ('musk', 'jensen', 'moderator', 'system'))
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id);

-- ---------------------------------------------------------------------------
-- 初始資料：兩位名人
-- ---------------------------------------------------------------------------
INSERT INTO persons (slug, name_zh, name_en, bio) VALUES
    (
        'elon_musk',
        '伊隆·馬斯克',
        'Elon Musk',
        'Tesla、SpaceX 等公司負責人，公開發言與訪談資料用於數位分身 RAG。'
    ),
    (
        'jensen_huang',
        '黃仁勳',
        'Jensen Huang',
        'NVIDIA 執行長，公開演講與訪談資料用於數位分身 RAG。'
    )
ON CONFLICT (slug) DO NOTHING;

COMMIT;
