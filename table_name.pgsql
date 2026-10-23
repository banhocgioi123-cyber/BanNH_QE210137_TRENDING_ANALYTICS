SELECT video_id, title, channel_title, view_count, like_count 
FROM fact_trending 
ORDER BY view_count DESC 
LIMIT 10;

Thống kê số lượng video trending theo Thể loại
SELECT 
    v.category_id, 
    COUNT(DISTINCT f.video_id) AS total_trending_videos
FROM fact_trending f
JOIN dim_videos v ON f.video_id = v.video_id
GROUP BY v.category_id
ORDER BY total_trending_videos DESC;

Thống kê Top 10 Kênh có nhiều video xuất hiện trên Trending nhất
SELECT 
    c.channel_id, 
    c.title AS channel_title, 
    COUNT(f.video_id) AS trending_count
FROM fact_trending f
JOIN dim_videos v ON f.video_id = v.video_id
JOIN dim_channels c ON v.channel_id = c.channel_id
GROUP BY c.channel_id, c.title
ORDER BY trending_count DESC
LIMIT 10;

Thống kê số lượng video theo từng Thể loại
SELECT 
    category_id, 
    COUNT(*) AS total_videos
FROM dim_videos
WHERE category_id IS NOT NULL
GROUP BY category_id
ORDER BY total_videos DESC;

Thống kê phân phối thời lượng video
SELECT 
    duration, 
    COUNT(*) AS count
FROM dim_videos
WHERE duration IS NOT NULL
GROUP BY duration
ORDER BY count DESC
LIMIT 15;

Thống kê Top 10 Kênh có số lượng Subcriber lớn nhất
SELECT 
    channel_id, 
    title AS channel_title, 
    subscriber_count
FROM dim_channels
ORDER BY subscriber_count DESC
LIMIT 10;

Theo dõi biến động tương tác (View, Like, Comment) từ bảng fact_stats
SELECT 
    video_id, 
    view_count, 
    like_count, 
    comment_count
FROM fact_stats
LIMIT 10;