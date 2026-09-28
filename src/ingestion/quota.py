"""Ngân sách quota theo ngày.

Google reset quota lúc nửa đêm giờ Thái Bình Dương (~14:00 hoặc 15:00 giờ VN),
nên "ngày quota" được tính theo múi giờ đó chứ không theo giờ VN.

Tổng unit đã dùng trong ngày được lưu ở state/quota/<ngày>.json trên MinIO,
để mọi lần chạy trong ngày (kể cả chạy song song) cộng dồn vào cùng một chỗ.
"""
import logging
from datetime import timedelta, timezone

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # Python < 3.9
    ZoneInfo, ZoneInfoNotFoundError = None, Exception

logger = logging.getLogger(__name__)

# Cứ dùng thêm bấy nhiêu unit thì đồng bộ con số lên MinIO một lần
SYNC_EVERY_UNITS = 50


class BudgetExceededError(Exception):
    """Lần gọi tiếp theo sẽ vượt ngân sách quota đặt cho job hiện tại."""


def _pacific_tz():
    try:
        return ZoneInfo("America/Los_Angeles")
    except (ZoneInfoNotFoundError, TypeError):
        # Windows thiếu dữ liệu múi giờ -> cần `pip install tzdata`.
        # Tạm dùng UTC-8: lệch 1 giờ vào mùa hè, vẫn an toàn nhờ phần dự phòng 500 unit.
        logger.warning("Không có dữ liệu múi giờ (thiếu gói tzdata) -> tạm dùng UTC-8")
        return timezone(timedelta(hours=-8))


def quota_day(moment):
    """Ngày quota (theo giờ Thái Bình Dương) của một thời điểm UTC, dạng 'YYYY-MM-DD'."""
    return moment.astimezone(_pacific_tz()).strftime("%Y-%m-%d")


class QuotaTracker:
    def __init__(self, storage, run_time):
        self.storage = storage
        self.key = f"state/quota/{quota_day(run_time)}.json"
        self.base = 0       # tổng đã ghi trên MinIO ở lần đồng bộ gần nhất
        self.pending = 0    # unit đã dùng nhưng chưa ghi lên MinIO

    @property
    def used_today(self):
        return self.base + self.pending

    def load(self):
        self.base = self.storage.get_json_or_default(self.key, {"units": 0})["units"]
        self.pending = 0
        return self.base

    def add(self, units):
        self.pending += units
        if self.pending >= SYNC_EVERY_UNITS:
            self.sync()

    def sync(self):
        """Đọc lại con số mới nhất rồi cộng phần của mình vào.

        Đọc lại ngay trước khi ghi giúp giảm sai lệch khi hai lần chạy chồng lên nhau
        (ví dụ trending chạy lúc 15:00 trong khi backfill đang chạy từ 14:30).
        """
        current = self.storage.get_json_or_default(self.key, {"units": 0})
        current["units"] = current.get("units", 0) + self.pending
        self.storage.put_json(self.key, current)
        self.base = current["units"]
        self.pending = 0
