-- =====================================================================
-- SQL kiểm tra dữ liệu sau khi nạp từ MinIO vào PostgreSQL (Report 2)
-- Chạy:  docker exec -i ady201m_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < configs/checks.sql
-- Các check "lỗi" mong đợi kết quả = 0.
-- =====================================================================
\pset footer off
-- Container Postgres mặc định chỉ có /dev/shm 64 MB: join song song lớn bị lỗi
-- 'could not resize shared memory segment'. Tắt song song cho phiên kiểm tra (docker-compose đã tăng shm_size).
SET max_parallel_workers_per_gather = 0;
\echo '=== 1. Số dòng mỗi bảng ==='
SELECT 'raw_files' AS bang, COUNT(*) AS so_dong FROM raw_files
UNION ALL SELECT 'categories',          COUNT(*) FROM categories
UNION ALL SELECT 'channels',            COUNT(*) FROM channels
UNION ALL SELECT 'videos',              COUNT(*) FROM videos
UNION ALL SELECT 'video_sources',       COUNT(*) FROM video_sources
UNION ALL SELECT 'video_stats',         COUNT(*) FROM video_stats
UNION ALL SELECT 'trending_snapshots',  COUNT(*) FROM trending_snapshots
UNION ALL SELECT 'playlist_items',      COUNT(*) FROM playlist_items
UNION ALL SELECT 'discover_candidates', COUNT(*) FROM discover_candidates;

\echo '=== 2. File raw đã nạp theo job (lineage MinIO -> DB) ==='
SELECT job, COUNT(*) AS so_file, SUM(n_items) AS so_item,
       MIN(captured_at) AS lan_dau, MAX(captured_at) AS lan_cuoi
FROM raw_files GROUP BY job ORDER BY job;

\echo '=== 3. Null ở cột quan trọng (videos) ==='
SELECT COUNT(*) FILTER (WHERE channel_id   IS NULL) AS null_channel_id,
       COUNT(*) FILTER (WHERE published_at IS NULL) AS null_published_at,
       COUNT(*) FILTER (WHERE title        IS NULL) AS null_title,
       COUNT(*) FILTER (WHERE category_id  IS NULL) AS null_category_id,
       COUNT(*) FILTER (WHERE duration_s   IS NULL) AS null_duration
FROM videos;

\echo '=== 4. Null số liệu tương tác (video_stats) — like/comment có thể bị chủ kênh ẩn ==='
SELECT COUNT(*) AS tong,
       COUNT(*) FILTER (WHERE view_count    IS NULL) AS null_view,
       ROUND(100.0 * COUNT(*) FILTER (WHERE like_count    IS NULL) / COUNT(*), 2) AS pct_null_like,
       ROUND(100.0 * COUNT(*) FILTER (WHERE comment_count IS NULL) / COUNT(*), 2) AS pct_null_comment
FROM video_stats;

\echo '=== 5. [LỖI] Trùng khoá chính (đã có PK chặn, kiểm tra lại cho chắc) ==='
SELECT 'videos' AS bang, COUNT(*) - COUNT(DISTINCT video_id) AS so_trung FROM videos
UNION ALL SELECT 'channels', COUNT(*) - COUNT(DISTINCT channel_id) FROM channels
UNION ALL SELECT 'video_stats', COUNT(*) - COUNT(DISTINCT (video_id, captured_at, source_job)) FROM video_stats;

\echo '=== 6. Lần chụp trước giờ đăng video, tách theo nguyên nhân ==='
-- livestream/premiere: YouTube đổi publishedAt sau khi phát xong -> dùng actual_start_time (đã xử lý ở labels.sql)
-- video thường: captured_at = lúc BẮT ĐẦU lượt crawl, API gọi muộn hơn vài phút -> lệch < 1 giờ là bình thường
-- [LỖI] thật sự: video thường lệch >= 1 giờ (mong đợi = 0)
SELECT CASE WHEN v.actual_start_time IS NOT NULL OR v.scheduled_start_time IS NOT NULL THEN 'livestream/premiere'
            WHEN v.published_at - s.captured_at < INTERVAL '1 hour' THEN 'video thuong, lech < 1h'
            ELSE '[LOI] video thuong, lech >= 1h' END AS nguyen_nhan,
       COUNT(*) AS so_dong,
       ROUND(MAX(EXTRACT(EPOCH FROM v.published_at - s.captured_at)) / 3600, 2) AS lech_lon_nhat_gio
FROM video_stats s JOIN videos v USING (video_id)
WHERE s.captured_at < v.published_at
GROUP BY 1 ORDER BY 1;

\echo '=== 7. View giảm giữa hai lần chụp liên tiếp (YouTube đôi khi lọc view ảo) ==='
WITH ordered AS (
    SELECT video_id, view_count,
           LAG(view_count) OVER (PARTITION BY video_id ORDER BY captured_at) AS prev_view
    FROM video_stats WHERE view_count IS NOT NULL
)
SELECT COUNT(*) FILTER (WHERE view_count < prev_view) AS so_lan_giam,
       COUNT(*) FILTER (WHERE prev_view IS NOT NULL)  AS so_cap_so_sanh,
       ROUND(100.0 * COUNT(*) FILTER (WHERE view_count < prev_view)
             / NULLIF(COUNT(*) FILTER (WHERE prev_view IS NOT NULL), 0), 3) AS pct_giam
FROM ordered;

\echo '=== 8. Kênh / danh mục TẠM (chưa có thông tin từ API) và video bị tạm bỏ khỏi phân tích ==='
SELECT (SELECT COUNT(*) FROM channels WHERE is_stub)                         AS kenh_tam,
       (SELECT COUNT(*) FROM videos v JOIN channels c USING (channel_id) WHERE c.is_stub) AS video_cua_kenh_tam,
       (SELECT COUNT(*) FROM categories WHERE title IS NULL)                 AS danh_muc_tam;

\echo '=== 8b. [LỖI] Vi phạm khoá ngoại (mong đợi = 0; đã có FK chặn, kiểm tra lại cho chắc) ==='
SELECT (SELECT COUNT(*) FROM videos v LEFT JOIN channels c USING (channel_id)
         WHERE v.channel_id IS NOT NULL AND c.channel_id IS NULL)            AS videos_khong_kenh,
       (SELECT COUNT(*) FROM videos v LEFT JOIN categories c USING (category_id)
         WHERE v.category_id IS NOT NULL AND c.category_id IS NULL)          AS videos_khong_danh_muc,
       (SELECT COUNT(*) FROM video_stats s LEFT JOIN videos v USING (video_id)
         WHERE v.video_id IS NULL)                                           AS stats_khong_video,
       (SELECT COUNT(*) FROM trending_snapshots t LEFT JOIN videos v USING (video_id)
         WHERE v.video_id IS NULL)                                           AS trending_khong_video;

\echo '=== 8c. Danh sách khoá ngoại trong schema ==='
SELECT tc.table_name AS bang, kcu.column_name AS cot,
       ccu.table_name AS tham_chieu_bang, ccu.column_name AS tham_chieu_cot, tc.constraint_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name
JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'
ORDER BY 1, 2;

\echo '=== 9. Khoảng trống giữa hai lần chụp trending chính (giờ) — crawler có chạy liên tục? ==='
WITH runs AS (SELECT DISTINCT captured_at FROM trending_snapshots WHERE source = 'main'),
gaps AS (SELECT captured_at, captured_at - LAG(captured_at) OVER (ORDER BY captured_at) AS gap FROM runs)
SELECT COUNT(*) AS so_lan_chup,
       ROUND(EXTRACT(EPOCH FROM PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY gap)) / 3600, 2) AS gap_trung_vi_gio,
       ROUND(EXTRACT(EPOCH FROM MAX(gap)) / 3600, 2) AS gap_lon_nhat_gio,
       COUNT(*) FILTER (WHERE gap > INTERVAL '3 hours') AS so_gap_tren_3h
FROM gaps;

\echo '=== 10. Số video mới (uploads) theo ngày đăng (giờ VN) ==='
SELECT (v.published_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE AS ngay_dang, COUNT(*) AS so_video
FROM videos v JOIN video_sources s ON s.video_id = v.video_id AND s.source_job = 'uploads/videos'
WHERE v.published_at >= '2026-09-20'
GROUP BY 1 ORDER BY 1;

\echo '=== 11. So sánh CÓ / KHÔNG CÓ backfill ==='
SELECT 'video khac nhau' AS chi_so,
       (SELECT COUNT(*) FROM videos) AS co_backfill,
       (SELECT COUNT(*) FROM v_videos_analysis) AS khong_backfill
UNION ALL SELECT 'dong video_stats',
       (SELECT COUNT(*) FROM video_stats), (SELECT COUNT(*) FROM v_stats_analysis)
UNION ALL SELECT 'kenh co video',
       (SELECT COUNT(DISTINCT channel_id) FROM videos),
       (SELECT COUNT(DISTINCT channel_id) FROM v_videos_analysis)
UNION ALL SELECT 'video tung len trending chinh',
       (SELECT COUNT(DISTINCT video_id) FROM trending_snapshots WHERE source = 'main'),
       (SELECT COUNT(DISTINCT t.video_id) FROM trending_snapshots t
         JOIN v_videos_analysis v USING (video_id) WHERE t.source = 'main')
UNION ALL SELECT 'video tung len trending danh muc',
       (SELECT COUNT(DISTINCT video_id) FROM trending_snapshots WHERE source = 'category'),
       (SELECT COUNT(DISTINCT t.video_id) FROM trending_snapshots t
         JOIN v_videos_analysis v USING (video_id) WHERE t.source = 'category')
UNION ALL SELECT 'video chi co o backfill',
       (SELECT COUNT(*) FROM videos) - (SELECT COUNT(*) FROM v_videos_analysis), 0;

\echo '=== 12. Cohort và tỉ lệ 2 nhãn (cửa sổ 72h) ==='
SELECT COUNT(*) AS cohort,
       COUNT(*) FILTER (WHERE is_trending_main) AS pos_main,
       ROUND(100.0 * COUNT(*) FILTER (WHERE is_trending_main) / COUNT(*), 3) AS pct_main,
       COUNT(is_trending_category) AS cohort_co_nhan_category,
       COUNT(*) FILTER (WHERE is_trending_category) AS pos_category,
       ROUND(100.0 * COUNT(*) FILTER (WHERE is_trending_category) / NULLIF(COUNT(is_trending_category), 0), 3) AS pct_category,
       COUNT(*) FILTER (WHERE is_trending_main AND is_trending_category) AS ca_hai_nhan
FROM v_video_labels;

\echo '=== 13. Tỉ lệ trending chính theo khung giờ đăng ==='
SELECT is_office_hours, COUNT(*) AS so_video,
       COUNT(*) FILTER (WHERE is_trending_main) AS pos_main,
       ROUND(100.0 * COUNT(*) FILTER (WHERE is_trending_main) / COUNT(*), 3) AS pct_main
FROM v_video_labels GROUP BY is_office_hours ORDER BY is_office_hours;

\echo '=== 14. Top 10 danh mục theo số video trending chính trong cohort ==='
SELECT category_id, category_title, COUNT(*) AS so_video,
       COUNT(*) FILTER (WHERE is_trending_main) AS pos_main,
       COUNT(*) FILTER (WHERE is_trending_category) AS pos_category
FROM v_video_labels GROUP BY 1, 2 ORDER BY pos_main DESC, so_video DESC LIMIT 10;
