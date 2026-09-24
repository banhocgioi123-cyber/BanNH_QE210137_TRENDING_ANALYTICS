"""Tải các file raw đang có trên MinIO nhưng chưa có ở data/raw về máy.

Dùng khi:
  - dữ liệu được cào trước lúc bật SAVE_LOCAL_COPY
  - thành viên nhóm vừa nhận bản mirror MinIO và muốn có bản local

Chạy từ thư mục gốc repo:
    python -m src.utils.sync_local
    python -m src.utils.sync_local --prefix raw/youtube/trending/
"""
import argparse

from src.utils.config import Config
from src.utils.minio_client import MinioStorage


def main():
    parser = argparse.ArgumentParser(description="Đồng bộ raw từ MinIO về data/raw")
    parser.add_argument("--prefix", default="raw/", help="Chỉ tải các key bắt đầu bằng prefix này")
    args = parser.parse_args()

    if not args.prefix.startswith("raw/"):
        parser.error("Chỉ đồng bộ tầng raw: prefix phải bắt đầu bằng 'raw/'")

    storage = MinioStorage()
    keys = storage.list_keys(args.prefix)

    downloaded = skipped = 0
    for key in keys:
        path = Config.LOCAL_DATA_DIR / key
        if path.exists():
            skipped += 1  # đã có bản local, bỏ qua
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        storage.client.fget_object(storage.bucket, key, str(path))
        downloaded += 1

    print(f"Tổng {len(keys)} file trên MinIO: tải mới {downloaded}, đã có sẵn {skipped}")
    print(f"Thư mục: {Config.LOCAL_DATA_DIR / 'raw'}")


if __name__ == "__main__":
    main()