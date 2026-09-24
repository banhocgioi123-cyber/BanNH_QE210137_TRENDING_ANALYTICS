"""Danh sách part xin từ API, chốt theo bài toán "thời điểm vàng".

Thêm/bớt part ở đây sẽ áp dụng cho mọi job (không tốn thêm quota).
"""

# videos.list
#   snippet              -> publishedAt (giờ upload), channelId, categoryId, title, defaultAudioLanguage
#   contentDetails       -> duration (tách Shorts / video dài)
#   statistics           -> viewCount, likeCount, commentCount
#   liveStreamingDetails -> giờ phát sóng thật của Premiere/livestream (kiểm tra độ lệch với publishedAt)
VIDEO_PARTS = "snippet,contentDetails,statistics,liveStreamingDetails"

# channels.list
#   snippet        -> publishedAt (tuổi kênh), country
#   statistics     -> subscriberCount, videoCount (biến kiểm soát quy mô kênh)
#   contentDetails -> relatedPlaylists.uploads (playlist chứa mọi video của kênh)
CHANNEL_PARTS = "snippet,statistics,contentDetails"

# playlistItems.list
#   contentDetails -> videoId, videoPublishedAt (chi tiết video lấy sau bằng videos.list)
PLAYLIST_ITEM_PARTS = "contentDetails"
