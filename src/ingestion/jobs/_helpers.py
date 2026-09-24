"""Hàm dùng chung cho các job: lưu raw, chia lô id, đọc/ghi file trạng thái."""
import logging
from datetime import datetime, timedelta, timezone

from src.ingestion.parts import VIDEO_PARTS
from src.ingestion.raw import build_key, make_envelope

logger = logging.getLogger(__name__)

# File trạng thái: dữ liệu TÍNH RA để điều khiển lần crawl sau, không phải raw
STATE_CHANNELS = "state/channels.json"
STATE_TRACKED_VIDEOS = "state/tracked_videos.json"


def save_raw(storage, config, run_time, job, endpoint, params, page_index, response):
    """Bọc response nguyên văn vào envelope rồi lưu lên MinIO. Trả về key."""
    key = build_key(job, run_time, config.CRAWLER_ID, page_index)
    storage.put_json(
        key, make_envelope(job, config.CRAWLER_ID, endpoint, params, page_index, response)
    )
    return key


def chunks(items, size=50):
    """Chia danh sách thành các lô (API cho tối đa 50 id mỗi lần gọi)."""
    items = list(items)
    for i in range(0, len(items), size):
        yield items[i:i + size]


def parse_utc(text):
    """'2026-09-24T01:00:03Z' -> datetime có múi giờ UTC."""
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def recent_dates(run_time, days):
    """Các ngày (UTC) từ hôm nay lùi về trước `days` ngày, dạng 'YYYY-MM-DD'."""
    return [(run_time - timedelta(days=d)).strftime("%Y-%m-%d") for d in range(days)]


def fetch_videos_by_ids(yt, storage, config, run_time, job, video_ids):
    """Gọi videos.list theo lô 50 id, lưu raw từng lô. Trả về (số file, danh sách item)."""
    saved, items = 0, []
    for page_index, batch in enumerate(chunks(sorted(video_ids))):
        params = {"part": VIDEO_PARTS, "id": ",".join(batch), "maxResults": 50}
        response = yt.call("videos", "list", **params)
        save_raw(storage, config, run_time, job, "videos.list", params, page_index, response)
        saved += 1
        items.extend(response.get("items", []))
    return saved, items
