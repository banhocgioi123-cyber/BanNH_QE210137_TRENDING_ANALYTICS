"""Lớp bọc YouTube Data API v3: thử lại khi lỗi tạm thời, đếm quota đã dùng."""
import json
import logging
import random
import time

import httplib2
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.ingestion.quota import BudgetExceededError

logger = logging.getLogger(__name__)

# Chi phí quota của các endpoint dùng trong dự án (đơn vị: unit)
QUOTA_COST = {
    "videos.list": 1,
    "channels.list": 1,
    "playlistItems.list": 1,
    "commentThreads.list": 1,
    "channelSections.list": 1,
    "search.list": 100,  # rất đắt: chỉ dùng trong job discover để TÌM KÊNH
}

# Lỗi 403 mang các lý do này nghĩa là hết quota trong ngày, thử lại vô ích
QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded"}


class QuotaExceededError(Exception):
    """Hết quota trong ngày, phải dừng crawl."""


def _error_reason(error):
    """Lấy trường 'reason' trong nội dung lỗi của Google API."""
    try:
        payload = json.loads(error.content.decode("utf-8"))
        return payload["error"]["errors"][0]["reason"]
    except (ValueError, KeyError, IndexError, AttributeError):
        return ""


class YouTubeClient:
    def __init__(self, api_key, max_retries=3, tracker=None):
        # API key truyền qua developerKey nên KHÔNG nằm trong params của request.
        # Nhờ vậy params có thể lưu thẳng vào envelope mà không lộ key.
        self.service = build("youtube", "v3", developerKey=api_key, cache_discovery=False)
        self.max_retries = max_retries
        self.units_used = 0       # unit dùng trong lần chạy này
        self.tracker = tracker    # QuotaTracker: tổng unit cả ngày (None = không giới hạn)
        self.limit = None         # trần unit cả ngày cho job hiện tại, crawler đặt trước mỗi job

    def call(self, resource, method, **params):
        """Gọi API, ví dụ call("videos", "list", part="snippet", id="abc").

        Trả về response nguyên văn (dict). Thử lại khi lỗi mạng hoặc lỗi 5xx/429.
        """
        endpoint = f"{resource}.{method}"

        cost = QUOTA_COST.get(endpoint, 1)

        for attempt in range(1, self.max_retries + 1):
            # Kiểm tra ngân sách TRƯỚC khi gửi request
            if self.tracker is not None and self.limit is not None:
                if self.tracker.used_today + cost > self.limit:
                    raise BudgetExceededError(
                        f"{endpoint} cần {cost} unit, hôm nay đã dùng "
                        f"{self.tracker.used_today}/{self.limit}"
                    )

            # Google tính quota cho mọi request gửi đi, kể cả request bị lỗi
            self.units_used += cost
            if self.tracker is not None:
                self.tracker.add(cost)
            try:
                request = getattr(getattr(self.service, resource)(), method)(**params)
                return request.execute()

            except HttpError as error:
                status = error.resp.status
                reason = _error_reason(error)

                if status == 403 and reason in QUOTA_REASONS:
                    raise QuotaExceededError(f"{endpoint}: {reason}") from error

                retryable = status in (429, 500, 502, 503, 504) or (
                    status == 403 and reason == "rateLimitExceeded"  # gọi quá nhanh, chờ là được
                )
                if retryable and attempt < self.max_retries:
                    self._wait(attempt, f"{endpoint} lỗi {status} {reason}")
                    continue

                # Lỗi 400/401/404... là lỗi của mình (sai tham số, sai key): dừng luôn
                raise

            except (OSError, httplib2.HttpLib2Error) as error:
                # Mất mạng, timeout, lỗi DNS...
                if attempt < self.max_retries:
                    self._wait(attempt, f"{endpoint} lỗi mạng: {error}")
                    continue
                raise

    @staticmethod
    def _wait(attempt, message):
        # Chờ tăng dần 2s, 4s, 8s... cộng thêm chút ngẫu nhiên
        delay = 2 ** attempt + random.uniform(0, 1)
        logger.warning("%s -> thử lại sau %.1fs (lần %d)", message, delay, attempt)
        time.sleep(delay)
