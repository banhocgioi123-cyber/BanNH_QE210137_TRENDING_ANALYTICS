"""Job stats: chụp lại view/like/comment của các video đang theo dõi.

Chuỗi snapshot cho phép tính 'view sau 24h/48h kể từ lúc đăng' -> biến kết quả
thay thế khi nhãn trending không đủ tin cậy.

Tần suất đề xuất: mỗi 3 giờ (cùng lịch với trending).
"""
import logging
from datetime import timedelta

from src.ingestion.jobs._helpers import STATE_TRACKED_VIDEOS, fetch_videos_by_ids, parse_utc

logger = logging.getLogger(__name__)

JOB_NAME = "stats"

# Theo dõi mỗi video trong bao nhiêu ngày kể từ lúc đăng
TRACK_DAYS = 7


def run(yt, storage, config, run_time):
    state = storage.get_json_or_default(STATE_TRACKED_VIDEOS, {"videos": {}})

    # Bỏ các video đã quá hạn theo dõi để quota không tăng mãi
    cutoff = run_time - timedelta(days=TRACK_DAYS)
    before = len(state["videos"])
    state["videos"] = {
        video_id: info for video_id, info in state["videos"].items()
        if parse_utc(info["published_at"]) >= cutoff
    }
    removed = before - len(state["videos"])
    if removed:
        storage.put_json(STATE_TRACKED_VIDEOS, state)
        logger.info("Ngừng theo dõi %d video quá %d ngày", removed, TRACK_DAYS)

    if not state["videos"]:
        logger.warning("Không có video nào để theo dõi -> hãy chạy job uploads trước")
        return 0

    saved, items = fetch_videos_by_ids(yt, storage, config, run_time, JOB_NAME, state["videos"])
    logger.info("Stats: %d file raw, %d/%d video còn truy cập được",
                saved, len(items), len(state["videos"]))
    return saved
