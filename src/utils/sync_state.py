"""Tải thư mục state/ (dữ liệu điều khiển của crawler) từ MinIO về máy.

Khác với raw/, các file trong state/ bị crawler GHI ĐÈ liên tục
(quota, danh sách kênh, video đang theo dõi...). Vì vậy script này
không bỏ qua file đã có, mà so nội dung với MinIO: khác thì tải lại.

Lưu ý: crawler luôn đọc state trực tiếp từ MinIO. Bản trên máy chỉ để
xem / sao lưu; sửa file local KHÔNG ảnh hưởng tới crawler.

Chạy từ thư mục gốc repo:
    python -m src.utils.sync_state
    python -m src.utils.sync_state --prefix state/quota/
    python -m src.utils.sync_state --mirror      # xoá file local không còn trên MinIO
"""
import argparse
import hashlib
import os

from src.utils.config import Config
from src.utils.minio_client import MinioStorage

STATE_PREFIX = "state/"


def _md5(path):
    """Tính MD5 của file local để so với ETag trên MinIO."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_unchanged(path, etag):
    """True nếu file local giống hệt object trên MinIO.

    ETag của object upload một lần (put_json) chính là MD5 nội dung.
    ETag có dấu '-' là upload nhiều phần -> không so được, coi như đã đổi.
    """
    if not path.exists() or not etag or "-" in etag:
        return False
    return _md5(path) == etag


def _download(storage, key, path):
    """Tải về file tạm rồi mới thay thế, tránh để lại file hỏng nếu bị ngắt giữa chừng."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    response = storage.client.get_object(storage.bucket, key)
    try:
        with open(tmp, "wb") as f:
            for chunk in response.stream(1024 * 1024):
                f.write(chunk)
    finally:
        response.close()
        response.release_conn()
    os.replace(tmp, path)  # os.replace ghi đè được cả trên Windows


def main():
    parser = argparse.ArgumentParser(description="Tải state/ từ MinIO về máy")
    parser.add_argument("--prefix", default=STATE_PREFIX,
                        help="Chỉ tải các key bắt đầu bằng prefix này (phải nằm trong state/)")
    parser.add_argument("--mirror", action="store_true",
                        help="Xoá file local trong phạm vi prefix nhưng không còn trên MinIO")
    args = parser.parse_args()

    if not args.prefix.startswith(STATE_PREFIX):
        parser.error("Prefix phải bắt đầu bằng 'state/'")

    storage = MinioStorage()
    # Lấy kèm ETag để so nội dung, không cần tải về mới biết có đổi hay không
    objects = list(storage.client.list_objects(storage.bucket, prefix=args.prefix, recursive=True))

    new = updated = unchanged = 0
    remote_paths = set()
    for obj in objects:
        key = obj.object_name
        path = Config.LOCAL_DATA_DIR / key
        remote_paths.add(path.resolve())
        etag = (obj.etag or "").strip('"')

        if _is_unchanged(path, etag):
            unchanged += 1
            continue
        existed = path.exists()
        _download(storage, key, path)
        if existed:
            updated += 1
        else:
            new += 1

    removed = 0
    local_root = Config.LOCAL_DATA_DIR / args.prefix
    if args.mirror and local_root.exists():
        for path in local_root.rglob("*"):
            if path.is_file() and path.resolve() not in remote_paths:
                path.unlink()
                removed += 1

    print(f"Tổng {len(objects)} file state trên MinIO: "
          f"mới {new}, cập nhật {updated}, không đổi {unchanged}")
    if args.mirror:
        print(f"Đã xoá {removed} file local không còn trên MinIO")
    print(f"Thư mục: {Config.LOCAL_DATA_DIR / STATE_PREFIX}")


if __name__ == "__main__":
    main()
