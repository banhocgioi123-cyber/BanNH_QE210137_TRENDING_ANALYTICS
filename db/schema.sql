-- =====================================================================
-- Schema PostgreSQL cho bộ export YouTube Trending (exports/us)
-- 7 bảng, tạo theo thứ tự cha -> con. Chạy lại nhiều lần vẫn an toàn.
-- =====================================================================

-- 1. channels: thông tin kênh (do job discover + channels ghi vào)
CREATE TABLE IF NOT EXISTS channels (
    channel_id           TEXT PRIMARY KEY,
    title                TEXT        NOT NULL,
    custom_url           TEXT,
    country              TEXT,
    default_language     TEXT,
    published_at         TIMESTAMPTZ NOT NULL,
    subscriber_count     BIGINT      NOT NULL,
    hidden_subscribers   BOOLEAN     NOT NULL,
    view_count           BIGINT      NOT NULL,
    video_count          BIGINT      NOT NULL,
    uploads_playlist_id  TEXT        NOT NULL UNIQUE,
    crawl_time           TIMESTAMPTZ NOT NULL,
    first_seen_at        TIMESTAMPTZ NOT NULL,
    source_job           TEXT        NOT NULL   -- 'discover/channels' | 'channels'
);

-- 2. videos: thông tin tĩnh của video
-- Không đặt FK channel_id -> channels vì dữ liệu hiện có 8 video
-- thuộc kênh chưa được cào (orphan).
CREATE TABLE IF NOT EXISTS videos (
    video_id                TEXT PRIMARY KEY,
    channel_id              TEXT        NOT NULL,
    title                   TEXT        NOT NULL,
    published_at            TIMESTAMPTZ NOT NULL,
    category_id             INTEGER     NOT NULL,
    default_language        TEXT,
    default_audio_language  TEXT,
    duration_seconds        INTEGER,
    definition              TEXT        NOT NULL,   -- 'hd' | 'sd'
    live_broadcast_content  TEXT        NOT NULL,   -- 'none' | 'upcoming' | 'live'
    scheduled_start_time    TIMESTAMPTZ,
    actual_start_time       TIMESTAMPTZ,
    actual_end_time         TIMESTAMPTZ,
    crawl_time              TIMESTAMPTZ NOT NULL,
    first_seen_at           TIMESTAMPTZ NOT NULL
);

-- 3. video_snapshots: số view/like/comment theo từng lần cào
-- (job: trending, stats, uploads/videos, backfill/videos)
CREATE TABLE IF NOT EXISTS video_snapshots (
    video_id       TEXT        NOT NULL REFERENCES videos (video_id),
    crawl_time     TIMESTAMPTZ NOT NULL,
    source_job     TEXT        NOT NULL,
    view_count     BIGINT      NOT NULL,
    like_count     BIGINT,                           -- NULL khi video ẩn lượt thích
    comment_count  BIGINT,                           -- NULL khi tắt bình luận
    PRIMARY KEY (video_id, crawl_time, source_job)
);

-- 4. trending_snapshots: thứ hạng trending của video theo từng lượt chạy
CREATE TABLE IF NOT EXISTS trending_snapshots (
    run_time       TIMESTAMPTZ NOT NULL,
    crawler_id     TEXT        NOT NULL,
    video_id       TEXT        NOT NULL REFERENCES videos (video_id),
    trending_rank  INTEGER     NOT NULL,
    region_code    TEXT        NOT NULL,
    PRIMARY KEY (run_time, crawler_id, video_id)
);

-- 5. playlist_items: video nào thuộc playlist uploads của kênh nào
-- Không đặt FK video_id -> videos vì phần backfill chưa lấy đủ chi tiết
-- video (hiện ~28 nghìn dòng chưa có trong bảng videos).
CREATE TABLE IF NOT EXISTS playlist_items (
    playlist_id         TEXT        NOT NULL REFERENCES channels (uploads_playlist_id),
    video_id            TEXT        NOT NULL,
    video_published_at  TIMESTAMPTZ NOT NULL,
    source_job          TEXT        NOT NULL,        -- 'uploads/playlist_items' | 'backfill/playlist_items'
    crawl_time          TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (playlist_id, video_id)
);

-- 6. discover_hits: kênh nào xuất hiện khi tìm kiếm từ khóa nào
-- Không đặt FK channel_id -> channels vì có 2 kênh chưa được lưu (orphan).
CREATE TABLE IF NOT EXISTS discover_hits (
    search_query          TEXT        NOT NULL,
    channel_id            TEXT        NOT NULL,
    search_rank           INTEGER     NOT NULL,
    channel_title         TEXT        NOT NULL,
    channel_published_at  TIMESTAMPTZ NOT NULL,
    region_code           TEXT        NOT NULL,
    relevance_language    TEXT        NOT NULL,
    crawl_time            TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (search_query, channel_id, crawl_time)
);

-- 7. channel_sections: các mục trên trang chủ của kênh
CREATE TABLE IF NOT EXISTS channel_sections (
    section_id        TEXT PRIMARY KEY,
    channel_id        TEXT        NOT NULL REFERENCES channels (channel_id),
    section_type      TEXT        NOT NULL,
    title             TEXT,
    section_position  INTEGER     NOT NULL,
    playlist_ids      TEXT[]      NOT NULL,          -- dạng {PL..., PL...}
    channel_ids       TEXT[]      NOT NULL,          -- dạng {} hoặc {UC...}
    crawl_time        TIMESTAMPTZ NOT NULL,
    first_seen_at     TIMESTAMPTZ NOT NULL
);

-- Index phục vụ các truy vấn JOIN thường gặp
CREATE INDEX IF NOT EXISTS idx_videos_channel_id          ON videos (channel_id);
CREATE INDEX IF NOT EXISTS idx_trending_video_id          ON trending_snapshots (video_id);
CREATE INDEX IF NOT EXISTS idx_playlist_items_video_id    ON playlist_items (video_id);
CREATE INDEX IF NOT EXISTS idx_discover_hits_channel_id   ON discover_hits (channel_id);
CREATE INDEX IF NOT EXISTS idx_channel_sections_channel   ON channel_sections (channel_id);
