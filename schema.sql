-- 1. Bảng Trending Videos
CREATE TABLE IF NOT EXISTS fact_trending (
    id SERIAL PRIMARY KEY,
    video_id VARCHAR(50),
    title TEXT,
    published_at TIMESTAMP,
    channel_id VARCHAR(50),
    channel_title TEXT,
    category_id INT,
    trending_date TIMESTAMP,
    tags TEXT,
    view_count BIGINT,
    like_count BIGINT,
    comment_count BIGINT,
    region_code VARCHAR(10) DEFAULT 'JP',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Bảng Channels Information
CREATE TABLE IF NOT EXISTS dim_channels (
    channel_id VARCHAR(50) PRIMARY KEY,
    title TEXT,
    description TEXT,
    custom_url TEXT,
    published_at TIMESTAMP,
    subscriber_count BIGINT,
    video_count INT,
    view_count BIGINT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Bảng Video Details & Metadata
CREATE TABLE IF NOT EXISTS dim_videos (
    video_id VARCHAR(50) PRIMARY KEY,
    channel_id VARCHAR(50),
    title TEXT,
    description TEXT,
    duration VARCHAR(20),
    definition VARCHAR(10),
    caption BOOLEAN,
    published_at TIMESTAMP
);

-- 4. Bảng Video Statistics (Stats)
CREATE TABLE IF NOT EXISTS fact_stats (
    id SERIAL PRIMARY KEY,
    video_id VARCHAR(50),
    view_count BIGINT,
    like_count BIGINT,
    comment_count BIGINT,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Bảng Playlist Items
CREATE TABLE IF NOT EXISTS dim_playlist_items (
    id SERIAL PRIMARY KEY,
    playlist_id VARCHAR(100),
    video_id VARCHAR(50),
    title TEXT,
    position INT,
    published_at TIMESTAMP
);

-- 6. Bảng Video Discoveries
CREATE TABLE IF NOT EXISTS fact_discover (
    id SERIAL PRIMARY KEY,
    video_id VARCHAR(50),
    keyword TEXT,
    rank INT,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);