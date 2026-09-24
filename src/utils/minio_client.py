"""Lớp bọc MinIO: tạo bucket nếu chưa có, ghi và đọc file JSON.

Nếu SAVE_LOCAL_COPY=true, mọi file raw còn được ghi thêm một bản vào data/raw/...
với cùng đường dẫn như trên MinIO. MinIO luôn là bản chính.
"""
import io
import json
import logging

from minio import Minio
from minio.error import S3Error

from src.utils.config import Config

logger = logging.getLogger(__name__)


class MinioStorage:
    def __init__(self, bucket=None):
        self.bucket = bucket or Config.MINIO_BUCKET
        self.client = Minio(
            Config.MINIO_ENDPOINT,
            access_key=Config.MINIO_ACCESS_KEY,
            secret_key=Config.MINIO_SECRET_KEY,
            secure=Config.MINIO_SECURE,
        )

    def ensure_bucket(self):
        """Tạo bucket nếu chưa tồn tại, để máy mới clone về vẫn chạy được ngay."""
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def put_json(self, key, data):
        """Ghi một dict thành file JSON (giữ nguyên tiếng Việt) lên MinIO."""
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.client.put_object(
            self.bucket,
            key,
            io.BytesIO(body),
            length=len(body),
            content_type="application/json; charset=utf-8",
        )
        # Chỉ sao lưu tầng raw; file state/ là dữ liệu điều khiển, không cần bản local
        if Config.SAVE_LOCAL_COPY and key.startswith("raw/"):
            self._save_local(key, body)
        return key

    @staticmethod
    def _save_local(key, body):
        """Ghi bản sao ra đĩa: key 'raw/youtube/...' -> data/raw/youtube/..."""
        path = Config.LOCAL_DATA_DIR / key
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        except OSError as error:
            # Bản local chỉ là bản phụ: lỗi ghi đĩa không được làm hỏng lần crawl
            logger.warning("Không ghi được bản local %s: %s", path, error)

    def get_json(self, key):
        """Đọc một file JSON từ MinIO về dạng dict."""
        response = self.client.get_object(self.bucket, key)
        try:
            return json.loads(response.read().decode("utf-8"))
        finally:
            response.close()
            response.release_conn()

    def get_json_or_default(self, key, default):
        """Đọc JSON; nếu object chưa tồn tại (lần chạy đầu) thì trả về default."""
        try:
            return self.get_json(key)
        except S3Error as error:
            if error.code == "NoSuchKey":
                return default
            raise

    def list_keys(self, prefix):
        """Liệt kê tên các object bắt đầu bằng prefix (duyệt cả thư mục con)."""
        objects = self.client.list_objects(self.bucket, prefix=prefix, recursive=True)
        return [obj.object_name for obj in objects]