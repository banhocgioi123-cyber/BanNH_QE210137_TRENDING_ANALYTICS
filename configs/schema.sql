-- =====================================================================
-- Schema PostgreSQL cho dữ liệu YouTube (tầng processing)
-- Nguồn: raw JSON trên MinIO (raw/youtube/<job>/dt=<ngày>/<crawler>_<HHMMSS>_pNN.json)
-- Chạy lại an toàn: chỉ tạo bảng/index nếu chưa có.
-- Quy ước: captured_at = mốc chụp lấy từ tên object (mọi trang của cùng một lần chạy chung mốc)
-- =====================================================================

-- Nhật ký file raw đã nạp: chứng minh dữ liệu đi từ MinIO vào DB, và để bỏ qua file đã nạp
CREATE TABLE IF NOT EXISTS raw_files (
    object_key      TEXT PRIMARY KEY,
    job             TEXT        NOT NULL,
    endpoint        TEXT,
    crawler_id      TEXT,
    captured_at     TIMESTAMPTZ NOT NULL,
    crawl_time_utc  TIMESTAMPTZ,
    page_index      INT,
    n_items         INT         NOT NULL DEFAULT 0,
    loaded_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Danh mục video của khu vực (videoCategories.list)
CREATE TABLE IF NOT EXISTS categories (
    category_id     INT PRIMARY KEY,
    title           TEXT,
    assignable      BOOLEAN
);

-- Kênh: bản mới nhất theo captured_at (từ channels.list của job channels và discover/channels)
CREATE TABLE IF NOT EXISTS channels (
    channel_id          TEXT PRIMARY KEY,
    title               TEXT,
    custom_url          TEXT,
    country             TEXT,
    default_language    TEXT,
    published_at        TIMESTAMPTZ,
    subscriber_count    BIGINT,
    hidden_subscriber   BOOLEAN,
    video_count         BIGINT,
    view_count          BIGINT,
    uploads_playlist    TEXT,
    first_source_job    TEXT,
    first_seen_at       TIMESTAMPTZ NOT NULL,
    last_seen_at        TIMESTAMPTZ NOT NULL
);

-- Video: metadata bản mới nhất theo captured_at (từ mọi response videos.list)
CREATE TABLE IF NOT EXISTS videos (
    video_id                TEXT PRIMARY KEY,
    channel_id              TEXT,
    published_at            TIMESTAMPTZ,
    title                   TEXT,
    description             TEXT,
    tags                    TEXT[],
    category_id             INT,
    default_language        TEXT,
    default_audio_language  TEXT,
    duration_s              INT,
    definition              TEXT,
    caption                 BOOLEAN,
    live_broadcast_content  TEXT,
    actual_start_time       TIMESTAMPTZ,
    scheduled_start_time    TIMESTAMPTZ,
    first_source_job        TEXT,
    first_seen_at           TIMESTAMPTZ NOT NULL,
    last_seen_at            TIMESTAMPTZ NOT NULL
);

-- Video được thấy ở job nào (dùng để lọc bỏ backfill ở tầng sử dụng)
CREATE TABLE IF NOT EXISTS video_sources (
    video_id            TEXT        NOT NULL,
    source_job          TEXT        NOT NULL,
    first_captured_at   TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (video_id, source_job)
);

-- Số liệu tương tác tại mỗi lần chụp
CREATE TABLE IF NOT EXISTS video_stats (
    video_id        TEXT        NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL,
    source_job      TEXT        NOT NULL,
    view_count      BIGINT,
    like_count      BIGINT,
    comment_count   BIGINT,
    PRIMARY KEY (video_id, captured_at, source_job)
);

-- Mỗi lần video xuất hiện trên bảng xếp hạng mostPopular
--   source = 'main'     : bảng chính (job trending), category_id = 0
--   source = 'category' : bảng theo danh mục (job trending_category)
CREATE TABLE IF NOT EXISTS trending_snapshots (
    video_id        TEXT        NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL,
    source          TEXT        NOT NULL CHECK (source IN ('main', 'category')),
    category_id     INT         NOT NULL,
    page_index      INT         NOT NULL,
    position        INT         NOT NULL,
    PRIMARY KEY (video_id, captured_at, source, category_id)
);

-- Danh sách video của kênh (playlistItems.list của uploads và backfill)
CREATE TABLE IF NOT EXISTS playlist_items (
    video_id            TEXT        NOT NULL,
    playlist_id         TEXT        NOT NULL,
    video_published_at  TIMESTAMPTZ,
    captured_at         TIMESTAMPTZ NOT NULL,
    source_job          TEXT        NOT NULL,
    PRIMARY KEY (video_id, playlist_id, captured_at)
);

-- Kênh ứng viên do discover tìm được (search theo từ khoá hoặc mục "kênh nổi bật")
CREATE TABLE IF NOT EXISTS discover_candidates (
    channel_id      TEXT        NOT NULL,
    method          TEXT        NOT NULL CHECK (method IN ('search', 'sections')),
    query_or_parent TEXT        NOT NULL,
    captured_at     TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (channel_id, method, query_or_parent, captured_at)
);

-- ---------------------------------------------------------------------
-- Dòng TẠM (stub) để khoá ngoại luôn hợp lệ mà không mất dữ liệu
--   Kênh: job trending chạy mỗi giờ nhưng job channels chỉ 2 lần/ngày, nên video trending
--   thường vào DB trước kênh của nó. Loader chèn kênh tạm (chỉ có channel_id, is_stub = true);
--   lần nạp channels.list sau đó điền đủ thông tin và đặt is_stub = false.
--   first_seen_at = 'infinity', last_seen_at = '-infinity' để bản thật luôn thắng khi upsert.
--   Danh mục: mã chưa có trong videoCategories.list (vd. 29) -> dòng tạm, title = NULL.
-- ---------------------------------------------------------------------
ALTER TABLE channels ADD COLUMN IF NOT EXISTS is_stub BOOLEAN NOT NULL DEFAULT false;

-- 29 = Nonprofits & Activism: video VN có dùng nhưng videoCategories.list(regionCode=VN) không trả về
INSERT INTO categories (category_id, title, assignable)
VALUES (29, 'Tổ chức phi lợi nhuận và Hoạt động xã hội', NULL)
ON CONFLICT (category_id) DO UPDATE SET title = COALESCE(categories.title, EXCLUDED.title);

-- Bù dòng tạm cho dữ liệu đã có (chạy lại an toàn; DB mới thì không làm gì)
INSERT INTO channels (channel_id, is_stub, first_source_job, first_seen_at, last_seen_at)
SELECT DISTINCT v.channel_id, true, 'stub', 'infinity'::TIMESTAMPTZ, '-infinity'::TIMESTAMPTZ
FROM videos v
WHERE v.channel_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM channels c WHERE c.channel_id = v.channel_id)
ON CONFLICT (channel_id) DO NOTHING;

INSERT INTO categories (category_id)
SELECT DISTINCT v.category_id
FROM videos v
WHERE v.category_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM categories c WHERE c.category_id = v.category_id)
ON CONFLICT (category_id) DO NOTHING;

-- ---------------------------------------------------------------------
-- Khoá ngoại (chỉ thêm nếu chưa có)
-- Không đặt khoá ngoại cho playlist_items / video_sources -> videos: 136k video chỉ có trong
-- playlist của kênh (video cũ, không gọi videos.list) nên không có dòng trong bảng videos.
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_videos_channel') THEN
        ALTER TABLE videos ADD CONSTRAINT fk_videos_channel
            FOREIGN KEY (channel_id) REFERENCES channels (channel_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_videos_category') THEN
        ALTER TABLE videos ADD CONSTRAINT fk_videos_category
            FOREIGN KEY (category_id) REFERENCES categories (category_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_video_stats_video') THEN
        ALTER TABLE video_stats ADD CONSTRAINT fk_video_stats_video
            FOREIGN KEY (video_id) REFERENCES videos (video_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_trending_video') THEN
        ALTER TABLE trending_snapshots ADD CONSTRAINT fk_trending_video
            FOREIGN KEY (video_id) REFERENCES videos (video_id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_videos_channel        ON videos (channel_id);
CREATE INDEX IF NOT EXISTS idx_videos_published      ON videos (published_at);
CREATE INDEX IF NOT EXISTS idx_sources_job           ON video_sources (source_job);
CREATE INDEX IF NOT EXISTS idx_trending_video_source ON trending_snapshots (video_id, source, captured_at);
CREATE INDEX IF NOT EXISTS idx_trending_captured     ON trending_snapshots (captured_at, source, category_id);
CREATE INDEX IF NOT EXISTS idx_raw_files_job         ON raw_files (job);
