-- =====================================================================
-- Tầng sử dụng: bỏ backfill, cohort và 2 nhãn trending tách riêng
-- Chạy lại an toàn: xoá view cũ rồi tạo lại (dữ liệu nằm ở bảng, view không chứa dữ liệu).
--
-- Nhãn (chốt 2026-10-21), cửa sổ 72 giờ kể từ release_at (giờ ra mắt thực tế):
--   is_trending_main     : có mặt trong bảng mostPopular chính (job trending)
--   is_trending_category : có mặt trong bảng mostPopular của một danh mục (job trending_category)
-- Hai nhãn độc lập, KHÔNG gộp; một video có thể có cả hai nhãn = 1.
-- =====================================================================

DROP VIEW IF EXISTS v_video_labels, v_cohort, v_trending_rank, v_videos_analysis, v_stats_analysis CASCADE;

-- Video dùng cho phân tích: thấy ở ít nhất một job KHÔNG phải backfill.
-- Backfill (lịch sử 30 ngày của kênh) vẫn nằm trong DB nhưng không có nhãn đáng tin.
-- Tạm bỏ video của kênh TẠM (chưa có thông tin kênh từ channels.list): thiếu feature kênh.
CREATE VIEW v_videos_analysis AS
SELECT v.*
FROM videos v
JOIN channels c ON c.channel_id = v.channel_id AND NOT c.is_stub
WHERE EXISTS (
    SELECT 1 FROM video_sources s
    WHERE s.video_id = v.video_id AND s.source_job NOT LIKE 'backfill/%'
);

-- Số liệu tương tác không tính các lần chụp của backfill, chỉ của video trong v_videos_analysis
CREATE VIEW v_stats_analysis AS
SELECT s.* FROM video_stats s
WHERE s.source_job NOT LIKE 'backfill/%'
  AND EXISTS (SELECT 1 FROM v_videos_analysis v WHERE v.video_id = s.video_id);

-- Thứ hạng trong từng lần chụp của từng bảng xếp hạng (1 = cao nhất)
CREATE VIEW v_trending_rank AS
SELECT t.*,
       ROW_NUMBER() OVER (PARTITION BY t.captured_at, t.source, t.category_id
                          ORDER BY t.page_index, t.position) AS rank
FROM trending_snapshots t;

-- Cohort: video mới do job uploads phát hiện, ra mắt trong khoảng trending chính được theo dõi đủ 72 giờ.
-- Video ra mắt trước lần chụp trending đầu tiên hoặc sau (lần chụp cuối - 72h) bị loại vì chưa quan sát đủ.
-- release_at = giờ khán giả thực sự xem được: livestream/premiere dùng actual_start_time
-- (YouTube đổi publishedAt của livestream thành lúc phát xong), video thường dùng published_at.
CREATE VIEW v_cohort AS
WITH crawl_range AS (
    SELECT MIN(captured_at) AS first_at, MAX(captured_at) AS last_at
    FROM trending_snapshots WHERE source = 'main'
)
SELECT v.*, COALESCE(v.actual_start_time, v.published_at) AS release_at
FROM videos v
JOIN video_sources s ON s.video_id = v.video_id AND s.source_job = 'uploads/videos'
CROSS JOIN crawl_range r
WHERE COALESCE(v.actual_start_time, v.published_at) >= r.first_at
  AND COALESCE(v.actual_start_time, v.published_at) <= r.last_at - INTERVAL '72 hours';

-- Bảng phân tích chính: mỗi dòng một video trong cohort, kèm feature cơ bản và 2 nhãn
CREATE VIEW v_video_labels AS
WITH category_range AS (
    SELECT MIN(captured_at) AS first_at, MAX(captured_at) AS last_at
    FROM trending_snapshots WHERE source = 'category'
),
hits AS (
    -- Lần đầu lên bảng và thứ hạng cao nhất trong 72 giờ đầu, tách theo nguồn
    SELECT r.video_id, r.source,
           MIN(r.captured_at) AS first_trending_at,
           MIN(r.rank)        AS best_rank
    FROM v_trending_rank r
    JOIN v_cohort c ON c.video_id = r.video_id
    WHERE r.captured_at BETWEEN c.release_at AND c.release_at + INTERVAL '72 hours'
    GROUP BY r.video_id, r.source
)
SELECT
    c.video_id,
    c.channel_id,
    c.published_at,
    c.release_at,
    c.release_at AT TIME ZONE 'Asia/Ho_Chi_Minh'                           AS release_at_vn,
    EXTRACT(HOUR   FROM c.release_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::INT AS publish_hour_vn,
    EXTRACT(ISODOW FROM c.release_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::INT AS publish_dow_vn,
    (EXTRACT(ISODOW FROM c.release_at AT TIME ZONE 'Asia/Ho_Chi_Minh') BETWEEN 1 AND 5
     AND EXTRACT(HOUR FROM c.release_at AT TIME ZONE 'Asia/Ho_Chi_Minh') BETWEEN 8 AND 16) AS is_office_hours,
    c.category_id,
    cat.title                         AS category_title,
    c.duration_s,
    c.live_broadcast_content,
    c.actual_start_time IS NOT NULL   AS is_live_or_premiere,
    c.definition,
    c.caption,
    c.default_audio_language,
    LENGTH(c.title)                   AS title_length,
    COALESCE(CARDINALITY(c.tags), 0)  AS n_tags,
    ch.subscriber_count               AS channel_subscribers,
    ch.video_count                    AS channel_video_count,
    ch.view_count                     AS channel_view_count,
    ch.country                        AS channel_country,
    -- Nhãn 1: bảng xếp hạng chính
    (m.video_id IS NOT NULL)                                          AS is_trending_main,
    EXTRACT(EPOCH FROM m.first_trending_at - c.release_at) / 3600.0 AS hours_to_trending_main,
    m.best_rank                                                       AS best_rank_main,
    -- Nhãn 2: bảng xếp hạng theo danh mục; NULL nếu video đăng ngoài khoảng job này được theo dõi đủ 72h
    CASE WHEN c.release_at BETWEEN cr.first_at AND cr.last_at - INTERVAL '72 hours'
         THEN (k.video_id IS NOT NULL) END                            AS is_trending_category,
    EXTRACT(EPOCH FROM k.first_trending_at - c.release_at) / 3600.0 AS hours_to_trending_category,
    k.best_rank                                                       AS best_rank_category
FROM v_cohort c
CROSS JOIN category_range cr
LEFT JOIN channels   ch  ON ch.channel_id = c.channel_id
LEFT JOIN categories cat ON cat.category_id = c.category_id
LEFT JOIN hits m ON m.video_id = c.video_id AND m.source = 'main'
LEFT JOIN hits k ON k.video_id = c.video_id AND k.source = 'category';
