"""Các job crawl. Mỗi job có hàm run(yt, storage, config, run_time) -> số file đã lưu.

Thứ tự phụ thuộc:  trending -> channels -> uploads -> stats
"""
from src.ingestion.jobs import channels, stats, trending, uploads

# Đăng ký job (giữ đúng thứ tự phụ thuộc)
JOBS = {
    "trending": trending.run,
    "channels": channels.run,
    "uploads": uploads.run,
    "stats": stats.run,
}
