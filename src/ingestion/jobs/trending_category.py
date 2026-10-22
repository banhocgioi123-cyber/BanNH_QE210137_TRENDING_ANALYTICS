"""Job trending_category: chụp mostPopular VN theo TỪNG danh mục (videoCategoryId).

Bảng trending chính chỉ có ~200 video/lần, mỗi danh mục lại có bảng xếp hạng riêng
-> thêm nhiều video trending (nhãn dương). Lưu tách khỏi job trending để tầng processing
phân biệt được is_trending_main (bảng chính) và is_trending_any (chính hoặc danh mục).

- Raw: raw/youtube/trending_category/... (videoCategories.list + videos.list mỗi danh mục)
- Danh mục không có bảng xếp hạng (API trả 400/404) thì bỏ qua.

Chi phí: 1 unit/trang. ~15 danh mục x <=4 trang ≈ 60 unit/lần.
Tần suất đề xuất: mỗi 3 giờ.
"""
import logging

from googleapiclient.errors import HttpError

from src.ingestion.jobs._helpers import save_raw
from src.ingestion.parts import VIDEO_PARTS

logger = logging.getLogger(__name__)

JOB_NAME = "trending_category"

# Chặn vòng lặp vô hạn nếu API trả nextPageToken bất thường
MAX_PAGES_PER_CATEGORY = 4


def list_categories(yt, storage, config, run_time, page_counter):
    """Lấy các danh mục gán được cho video ở khu vực này (1 unit)."""
    params = {"part": "snippet", "regionCode": config.REGION_CODE, "hl": "vi"}
    response = yt.call("videoCategories", "list", **params)
    save_raw(storage, config, run_time, JOB_NAME, "videoCategories.list",
             params, page_counter[0], response)
    page_counter[0] += 1
    return [item["id"] for item in response.get("items", [])
            if item.get("snippet", {}).get("assignable")]


def run(yt, storage, config, run_time):
    page_counter = [0]  # đánh số trang liên tục cho mọi file của lần chạy này
    categories = list_categories(yt, storage, config, run_time, page_counter)
    video_ids, skipped = set(), []

    for category_id in categories:
        page_token = None
        for _ in range(MAX_PAGES_PER_CATEGORY):
            params = {
                "part": VIDEO_PARTS,
                "chart": "mostPopular",
                "regionCode": config.REGION_CODE,
                "videoCategoryId": category_id,
                "maxResults": 50,
            }
            if page_token:
                params["pageToken"] = page_token

            try:
                response = yt.call("videos", "list", **params)
            except HttpError as error:
                # Danh mục không có bảng xếp hạng ở khu vực này
                if error.resp.status in (400, 404):
                    skipped.append(category_id)
                    break
                raise

            save_raw(storage, config, run_time, JOB_NAME, "videos.list",
                     params, page_counter[0], response)
            page_counter[0] += 1
            video_ids.update(item["id"] for item in response.get("items", []))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

    logger.info("Trending theo danh mục: %d danh mục (bỏ qua %s), %d file, %d video khác nhau",
                len(categories) - len(skipped), skipped or "không", page_counter[0], len(video_ids))
    return page_counter[0]
