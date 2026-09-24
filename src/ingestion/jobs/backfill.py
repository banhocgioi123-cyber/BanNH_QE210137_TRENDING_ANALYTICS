"""Job backfill: lấy lùi video trong BACKFILL_DAYS ngày gần nhất của mọi kênh đang theo dõi.

Mục đích: tăng số video khác nhau (mục tiêu ~100k). Video lịch sử KHÔNG có nhãn
trending (lúc đó chưa chụp), chỉ dùng được tổng view -> phân tích theo lượt xem.

- Raw:   raw/youtube/backfill/playlist_items/... và raw/youtube/backfill/videos/...
- State: state/backfill.json = {channel_id: thời điểm đã backfill xong}

Mỗi kênh chỉ backfill 1 lần. Chạy lại job sẽ tự làm tiếp các kênh chưa xong
(bị ngắt giữa chừng, hoặc kênh mới do job discover thêm vào).
Video backfill KHÔNG được đưa vào danh sách của job stats.
"""
import logging
from datetime import timedelta

from googleapiclient.errors import HttpError

from src.ingestion.jobs._helpers import (
    STATE_BACKFILL, STATE_CHANNELS, fetch_videos_by_ids, fmt_utc, parse_utc, save_raw,
)
from src.ingestion.parts import PLAYLIST_ITEM_PARTS

logger = logging.getLogger(__name__)

JOB_PLAYLIST = "backfill/playlist_items"
JOB_VIDEOS = "backfill/videos"

# Lấy lùi bao nhiêu ngày
BACKFILL_DAYS = 90
# Số trang playlist tối đa mỗi kênh (50 video/trang) -> tối đa 200 video/kênh.
# Giới hạn này để vài kênh đăng rất nhiều (tin tức...) không áp đảo dữ liệu train.
MAX_PAGES_PER_CHANNEL = 4
# Số kênh xử lý mỗi lần chạy. Ngân sách quota theo ngày sẽ tự dừng job sớm hơn nếu cần.
MAX_CHANNELS_PER_RUN = 1000
# Cứ xử lý xong bấy nhiêu kênh thì lấy chi tiết video và lưu tiến độ một lần
CHECKPOINT_EVERY = 20


def scan_playlist(yt, storage, config, run_time, playlist_id, cutoff, page_counter):
    """Quét playlist uploads của một kênh, trả về tập videoId đăng sau `cutoff`."""
    video_ids = set()
    page_token = None

    for _ in range(MAX_PAGES_PER_CHANNEL):
        params = {"part": PLAYLIST_ITEM_PARTS, "playlistId": playlist_id, "maxResults": 50}
        if page_token:
            params["pageToken"] = page_token

        response = yt.call("playlistItems", "list", **params)
        save_raw(storage, config, run_time, JOB_PLAYLIST, "playlistItems.list",
                 params, page_counter[0], response)
        page_counter[0] += 1

        reached_old_video = False
        for item in response.get("items", []):
            details = item.get("contentDetails", {})
            published = details.get("videoPublishedAt")
            if not published:
                continue  # video riêng tư/đã xoá
            if parse_utc(published) >= cutoff:
                video_ids.add(details["videoId"])
            else:
                reached_old_video = True

        page_token = response.get("nextPageToken")
        # Playlist uploads xếp mới -> cũ: gặp video quá hạn là dừng
        if reached_old_video or not page_token:
            break

    return video_ids


def run(yt, storage, config, run_time):
    channels = storage.get_json_or_default(STATE_CHANNELS, {"channels": {}})["channels"]
    state = storage.get_json_or_default(STATE_BACKFILL, {"done": {}})
    done = state["done"]

    todo = [cid for cid in sorted(channels) if cid not in done][:MAX_CHANNELS_PER_RUN]
    remaining = len([cid for cid in channels if cid not in done]) - len(todo)
    if not todo:
        logger.info("Tất cả %d kênh đã backfill xong", len(channels))
        return 0
    logger.info("Backfill %d kênh lần này (%d ngày), còn %d kênh cho lần sau",
                len(todo), BACKFILL_DAYS, remaining)

    cutoff = run_time - timedelta(days=BACKFILL_DAYS)
    playlist_pages = [0]   # bộ đếm trang dùng chung (list để hàm con cập nhật được)
    video_pages = 0
    files = 0
    total_videos = 0
    buffer_ids, buffer_channels = set(), []

    def flush():
        """Lấy chi tiết video trong buffer, rồi đánh dấu các kênh tương ứng là xong."""
        nonlocal video_pages, files, total_videos
        if buffer_ids:
            n_files, _ = fetch_videos_by_ids(yt, storage, config, run_time, JOB_VIDEOS,
                                             buffer_ids, start_page=video_pages)
            video_pages += n_files
            files += n_files
            total_videos += len(buffer_ids)
        for channel_id in buffer_channels:
            done[channel_id] = fmt_utc(run_time)
        state["updated_at_utc"] = fmt_utc(run_time)
        storage.put_json(STATE_BACKFILL, state)
        buffer_ids.clear()
        buffer_channels.clear()

    for index, channel_id in enumerate(todo, start=1):
        playlist_id = channels[channel_id]["uploads_playlist"]
        before = playlist_pages[0]
        try:
            buffer_ids |= scan_playlist(yt, storage, config, run_time,
                                        playlist_id, cutoff, playlist_pages)
        except HttpError as error:
            if error.resp.status != 404:
                raise
            # Kênh xoá/ẩn playlist: đánh dấu xong để không thử lại mãi
            logger.warning("Không tìm thấy playlist %s của kênh %s", playlist_id, channel_id)
        files += playlist_pages[0] - before
        buffer_channels.append(channel_id)

        if index % CHECKPOINT_EVERY == 0:
            flush()
            logger.info("Tiến độ: %d/%d kênh, %d video", index, len(todo), total_videos)

    flush()
    logger.info("Backfill: %d file raw, %d video từ %d kênh (còn %d kênh)",
                files, total_videos, len(todo), remaining)
    return files
