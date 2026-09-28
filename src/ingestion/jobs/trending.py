"""Job trending: chụp danh sách mostPopular của khu vực, mỗi trang lưu thành một file.

Tần suất đề xuất: mỗi 3 giờ (video có thể chỉ trending vài giờ).
"""
import logging

from src.ingestion.jobs._helpers import save_raw
from src.ingestion.parts import VIDEO_PARTS

logger = logging.getLogger(__name__)

JOB_NAME = "trending"

# Chặn vòng lặp vô hạn nếu API trả nextPageToken bất thường
MAX_PAGES = 10


def run(yt, storage, config, run_time):
    page_token = None
    saved = 0
    total_items = 0

    for page_index in range(MAX_PAGES):
        params = {
            "part": VIDEO_PARTS,
            "chart": "mostPopular",
            "regionCode": config.REGION_CODE,
            "maxResults": 50,
        }
        if page_token:
            params["pageToken"] = page_token

        response = yt.call("videos", "list", **params)
        key = save_raw(storage, config, run_time, JOB_NAME, "videos.list", params, page_index, response)

        n_items = len(response.get("items", []))
        saved += 1
        total_items += n_items
        logger.info("Đã lưu %s (%d video)", key, n_items)

        page_token = response.get("nextPageToken")
        if not page_token:
            break
    else:
        logger.warning("Dừng ở %d trang do chạm MAX_PAGES", MAX_PAGES)

    logger.info("Trending: %d trang, %d video", saved, total_items)
    return saved
