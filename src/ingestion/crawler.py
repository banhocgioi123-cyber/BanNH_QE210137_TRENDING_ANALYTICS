"""Điểm chạy crawl.

Chạy từ thư mục gốc repo:
    python -m src.ingestion.crawler --job trending                  # mỗi giờ
    python -m src.ingestion.crawler --job stats                     # mỗi 3 giờ
    python -m src.ingestion.crawler --job channels uploads          # 09:00 và 21:00
    python -m src.ingestion.crawler --job discover backfill         # 14:30 (sau khi quota reset)

Nhiều job chạy lần lượt theo thứ tự ghi.

Ngân sách quota theo ngày (xem QUOTA_* trong .env):
  - Job nặng (discover, backfill) dừng khi tổng cả ngày chạm BUDGET - RESERVE;
    crawler bỏ qua job đó và chạy tiếp các job sau (tiến độ đã được lưu).
  - Job thiết yếu dừng khi chạm BUDGET.

Exit code: 0 = thành công (kể cả khi job nặng dừng vì đủ ngân sách),
           1 = lỗi, 2 = hết quota / job thiết yếu chạm ngân sách.
"""
import argparse
import logging
import sys
from pathlib import Path

from src.ingestion.jobs import JOBS
from src.ingestion.quota import BudgetExceededError, QuotaTracker
from src.ingestion.raw import utc_now
from src.ingestion.youtube_client import QuotaExceededError, YouTubeClient
from src.utils.config import Config
from src.utils.minio_client import MinioStorage

logger = logging.getLogger("crawler")

# Job tốn nhiều quota, chạy được đến đâu hay đến đó; lần sau tự làm tiếp
HEAVY_JOBS = {"discover", "backfill"}


def setup_logging(run_time):
    """Ghi log ra màn hình và ra file logs/crawl_<ngày>.log."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"crawl_{run_time:%Y-%m-%d}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    # Thư viện Google log rất nhiều ở mức INFO, chỉ giữ cảnh báo
    logging.getLogger("googleapiclient").setLevel(logging.WARNING)


def job_limit(job):
    """Trần tổng unit cả ngày mà job này được phép chạm tới."""
    if job in HEAVY_JOBS:
        return Config.QUOTA_DAILY_BUDGET - Config.QUOTA_CORE_RESERVE
    return Config.QUOTA_DAILY_BUDGET


def main():
    parser = argparse.ArgumentParser(description="Crawl YouTube -> MinIO (raw JSON)")
    parser.add_argument("--job", required=True, nargs="+", choices=list(JOBS),
                        help="Một hoặc nhiều job, chạy theo thứ tự ghi")
    args = parser.parse_args()

    run_time = utc_now()
    setup_logging(run_time)
    logger.info("=== Bắt đầu: %s (run_time UTC %s) ===", " -> ".join(args.job), run_time.isoformat())

    yt = None
    tracker = None
    current = None
    try:
        Config.validate()

        storage = MinioStorage()
        storage.ensure_bucket()

        tracker = QuotaTracker(storage, run_time)
        tracker.load()
        logger.info("Quota ngày %s (giờ Thái Bình Dương): đã dùng %d/%d unit",
                    tracker.key.rsplit("/", 1)[-1][:-5], tracker.used_today,
                    Config.QUOTA_DAILY_BUDGET)

        yt = YouTubeClient(Config.YOUTUBE_API_KEY, tracker=tracker)
        for current in args.job:
            yt.limit = job_limit(current)
            logger.info("--- Job '%s' (trần hôm nay %d unit) ---", current, yt.limit)
            try:
                saved = JOBS[current](yt, storage, Config, run_time)
            except BudgetExceededError as error:
                if current not in HEAVY_JOBS:
                    raise
                # Job nặng: dừng an toàn, tiến độ đã lưu, để dành quota cho job thiết yếu
                logger.warning("Job '%s' dừng vì đủ ngân sách hôm nay (%s). "
                               "Lần chạy sau sẽ làm tiếp.", current, error)
                continue
            finally:
                tracker.sync()
            logger.info("--- Job '%s' xong: %d file ---", current, saved)

        logger.info("=== Hoàn tất ===")
        return 0

    except BudgetExceededError as error:
        logger.error("Job thiết yếu '%s' chạm ngân sách ngày: %s", current, error)
        return 2

    except QuotaExceededError as error:
        logger.error("Hết quota YouTube API (job '%s'): %s", current, error)
        return 2

    except Exception:
        # logger.exception ghi cả traceback để biết lỗi ở đâu
        logger.exception("Job '%s' thất bại", current)
        return 1

    finally:
        if yt is not None:
            logger.info("Quota: lần chạy này %d unit, cả ngày %d/%d unit",
                        yt.units_used, tracker.used_today, Config.QUOTA_DAILY_BUDGET)


if __name__ == "__main__":
    sys.exit(main())
