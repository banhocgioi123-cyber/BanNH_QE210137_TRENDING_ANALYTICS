"""Đọc cấu hình từ file .env ở thư mục gốc repo."""
import os
import re
from pathlib import Path

from dotenv import load_dotenv

# Tự tìm file .env bằng cách đi ngược lên từ thư mục chứa file này
load_dotenv()


def _get_bool(name, default="false"):
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


class Config:
    # YouTube
    YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
    REGION_CODE = os.getenv("REGION_CODE", "VN").strip()
    CRAWLER_ID = os.getenv("CRAWLER_ID", "").strip()

    # MinIO
    MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000").strip()
    MINIO_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "").strip()
    MINIO_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "").strip()
    MINIO_BUCKET = os.getenv("MINIO_BUCKET", "youtube-raw").strip()
    MINIO_SECURE = _get_bool("MINIO_SECURE")

    # Bản sao local: file raw được ghi thêm vào <LOCAL_DATA_DIR>/raw/... (MinIO vẫn là bản chính)
    SAVE_LOCAL_COPY = _get_bool("SAVE_LOCAL_COPY", "true")
    # Đường dẫn tương đối được tính từ thư mục gốc repo, không phụ thuộc chỗ đứng khi chạy lệnh
    REPO_ROOT = Path(__file__).resolve().parents[2]
    LOCAL_DATA_DIR = REPO_ROOT / os.getenv("LOCAL_DATA_DIR", "data").strip()

    @classmethod
    def validate(cls):
        """Dừng sớm với thông báo rõ ràng nếu .env thiếu hoặc sai."""
        missing = [
            name for name, value in {
                "YOUTUBE_API_KEY": cls.YOUTUBE_API_KEY,
                "CRAWLER_ID": cls.CRAWLER_ID,
                "MINIO_ROOT_USER": cls.MINIO_ACCESS_KEY,
                "MINIO_ROOT_PASSWORD": cls.MINIO_SECRET_KEY,
            }.items() if not value
        ]
        if missing:
            raise ValueError(f"Thiếu biến trong .env: {', '.join(missing)}")

        # CRAWLER_ID nằm trong tên object trên MinIO nên chỉ cho phép ký tự an toàn
        if not re.fullmatch(r"[a-z0-9_-]+", cls.CRAWLER_ID):
            raise ValueError("CRAWLER_ID chỉ được chứa chữ thường, số, '_' hoặc '-'")