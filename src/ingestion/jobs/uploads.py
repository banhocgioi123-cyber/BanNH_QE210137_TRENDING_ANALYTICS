"""Job uploads: lấy MỌI video mới đăng của các kênh đang theo dõi (nhóm so sánh).

Video nào sau này xuất hiện trong trending -> nhóm trending; còn lại -> non-trending.
Việc gắn nhãn làm ở tầng processing, job này chỉ thu thập.

- Raw: playlistItems.list (danh sách video của kênh) + videos.list (chi tiết video mới).
- State: thêm video mới vào state/tracked_videos.json để job stats theo dõi view.

Tần suất đề xuất: 1 lần/ngày, chạy SAU job channels.
"""
import logging
from datetime import timedelta

from googleapiclient.errors import HttpError

from src.ingestion.jobs._helpers import (
    STATE_CHANNELS, STATE_TRACKED_VIDEOS, fetch_videos_by_ids, parse_utc, save_raw,
)
from src.ingestion.parts import PLAYLIST_ITEM_PARTS

logger = logging.getLogger(__name__)

JOB_PLAYLIST = "uploads/playlist_items"
JOB_VIDEOS = "uploads/videos"

# Chỉ quét kênh có mặt trong trending trong vòng bao nhiêu ngày gần nhất
CHANNEL_ACTIVE_DAYS = 30
# Video đăng trong bao nhiêu ngày gần nhất thì đưa vào theo dõi
UPLOAD_LOOKBACK_DAYS = 7
# Số trang playlist tối đa mỗi kênh (kênh đăng rất nhiều như kênh tin tức)
MAX_PAGES_PER_CHANNEL = 4


def active_playlists(state, run_time):
    """Lọc các kênh còn 'hoạt động' trong trending gần đây."""
    cutoff = run_time - timedelta(days=CHANNEL_ACTIVE_DAYS)
    return {
        channel_id: info["uploads_playlist"]
        for channel_id, info in state.get("channels", {}).items()
        if parse_utc(info["last_seen_utc"]) >= cutoff
    }


def run(yt, storage, config, run_time):
    playlists = active_playlists(storage.get_json_or_default(STATE_CHANNELS, {}), run_time)
    if not playlists:
        logger.warning("Chưa có state kênh -> hãy chạy job channels trước")
        return 0
    logger.info("Quét uploads của %d kênh", len(playlists))

    cutoff = run_time - timedelta(days=UPLOAD_LOOKBACK_DAYS)
    new_videos = {}  # video_id -> {channel_id, published_at}
    saved = 0
    page_index = 0  # đánh số liên tục cho mọi file playlist của lần chạy này

    for channel_id, playlist_id in sorted(playlists.items()):
        page_token = None
        for _ in range(MAX_PAGES_PER_CHANNEL):
            params = {"part": PLAYLIST_ITEM_PARTS, "playlistId": playlist_id, "maxResults": 50}
            if page_token:
                params["pageToken"] = page_token

            try:
                response = yt.call("playlistItems", "list", **params)
            except HttpError as error:
                # Kênh xoá/ẩn playlist: bỏ qua kênh này, không làm hỏng cả job
                if error.resp.status == 404:
                    logger.warning("Không tìm thấy playlist %s của kênh %s", playlist_id, channel_id)
                    break
                raise

            # Lưu TOÀN BỘ response, việc lọc 7 ngày chỉ để quyết định gọi tiếp
            save_raw(storage, config, run_time, JOB_PLAYLIST, "playlistItems.list",
                     params, page_index, response)
            saved += 1
            page_index += 1

            reached_old_video = False
            for item in response.get("items", []):
                details = item.get("contentDetails", {})
                published = details.get("videoPublishedAt")
                if not published:
                    continue  # video riêng tư/đã xoá không có ngày đăng
                if parse_utc(published) >= cutoff:
                    new_videos[details["videoId"]] = {
                        "channel_id": channel_id, "published_at": published,
                    }
                else:
                    reached_old_video = True

            page_token = response.get("nextPageToken")
            # Playlist uploads xếp mới -> cũ: gặp video cũ là đủ, khỏi lấy trang sau
            if reached_old_video or not page_token:
                break

    logger.info("Có %d video đăng trong %d ngày gần nhất", len(new_videos), UPLOAD_LOOKBACK_DAYS)

    # Lấy chi tiết (giờ đăng, thời lượng, view...) của các video mới
    n_files, _ = fetch_videos_by_ids(yt, storage, config, run_time, JOB_VIDEOS, new_videos)
    saved += n_files

    # Cập nhật danh sách video cần job stats theo dõi
    state = storage.get_json_or_default(STATE_TRACKED_VIDEOS, {"videos": {}})
    added = 0
    for video_id, info in new_videos.items():
        if video_id not in state["videos"]:
            state["videos"][video_id] = {
                **info, "first_seen_utc": run_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            added += 1
    state["updated_at_utc"] = run_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    storage.put_json(STATE_TRACKED_VIDEOS, state)

    logger.info("Uploads: %d file raw, thêm %d video vào danh sách theo dõi", saved, added)
    return saved
