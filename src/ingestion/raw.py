"""Quy ước chung của tầng Raw: tên object trên MinIO và envelope bọc response."""
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc)


def build_key(job, run_time, crawler_id, page_index):
    """Tên object: raw/youtube/<job>/dt=<ngày UTC>/<crawler_id>_<HHMMSS>_p<trang>.json

    Mọi trang của cùng một lần chạy dùng chung run_time nên nằm cạnh nhau.
    crawler_id giúp gộp dữ liệu từ nhiều máy mà không bị đè file.
    """
    return (
        f"raw/youtube/{job}/dt={run_time:%Y-%m-%d}/"
        f"{crawler_id}_{run_time:%H%M%S}_p{page_index:02d}.json"
    )


def make_envelope(job, crawler_id, endpoint, params, page_index, response):
    """Bọc response NGUYÊN VĂN của API cùng metadata. Không sửa gì bên trong response."""
    return {
        "crawler_id": crawler_id,
        "job": job,
        "crawl_time_utc": utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "request": {"endpoint": endpoint, "params": params},
        "page_index": page_index,
        "response": response,
    }
