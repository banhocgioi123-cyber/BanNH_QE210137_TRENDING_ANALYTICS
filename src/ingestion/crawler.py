"""Điểm chạy crawl.

Chạy từ thư mục gốc repo:
    python -m src.ingestion.crawler --job trending
    python -m src.ingestion.crawler --job trending stats        # mỗi 3 giờ
    python -m src.ingestion.crawler --job channels uploads      # 1 lần/ngày

Nhiều job chạy lần lượt theo thứ tự ghi; job nào lỗi thì dừng luôn các job sau.
Exit code: 0 = thành công, 1 = lỗi, 2 = hết quota.
"""
import argparse
import logging
import sys
from pathlib import Path

from src.ingestion.jobs import JOBS
from src.ingestion.raw import utc_now
from src.ingestion.youtube_client import QuotaExceededError, YouTubeClient
from src.utils.config import Config
from src.utils.minio_client import MinioStorage

logger = logging.getLogger("crawler")


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


def main():
    parser = argparse.ArgumentParser(description="Crawl YouTube -> MinIO (raw JSON)")
    parser.add_argument("--job", required=True, nargs="+", choices=list(JOBS),
                        help="Một hoặc nhiều job, chạy theo thứ tự ghi")
    args = parser.parse_args()

    run_time = utc_now()
    setup_logging(run_time)
    logger.info("=== Bắt đầu: %s (run_time UTC %s) ===", " -> ".join(args.job), run_time.isoformat())

    yt = None
    current = None
    try:
        Config.validate()

        storage = MinioStorage()
        storage.ensure_bucket()

        yt = YouTubeClient(Config.YOUTUBE_API_KEY)
        for current in args.job:
            logger.info("--- Job '%s' ---", current)
            saved = JOBS[current](yt, storage, Config, run_time)
            logger.info("--- Job '%s' xong: %d file ---", current, saved)

        logger.info("=== Hoàn tất ===")
        return 0

    except QuotaExceededError as error:
        logger.error("Hết quota YouTube API (job '%s'): %s", current, error)
        return 2

    except Exception:
        # logger.exception ghi cả traceback để biết lỗi ở đâu
        logger.exception("Job '%s' thất bại", current)
        return 1

    finally:
        if yt is not None:
            logger.info("Tổng quota đã dùng trong lần chạy: %d unit", yt.units_used)


if __name__ == "__main__":
    sys.exit(main())
