"""Các job crawl. Mỗi job có hàm run(yt, storage, config, run_time) -> số file đã lưu.

Thứ tự phụ thuộc:
    trending -> channels -> discover -> uploads -> stats
                                     -> backfill (dùng chung state kênh, chạy riêng)
"""
from src.ingestion.jobs import backfill, channels, discover, stats, trending, uploads

# Đăng ký job (giữ đúng thứ tự phụ thuộc)
JOBS = {
    "trending": trending.run,
    "channels": channels.run,
    "discover": discover.run,
    "uploads": uploads.run,
    "backfill": backfill.run,
    "stats": stats.run,
}
