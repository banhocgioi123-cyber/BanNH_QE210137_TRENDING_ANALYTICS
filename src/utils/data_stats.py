"""Thống kê nhanh số lượng dữ liệu đang có trong bản local data/raw/.

Chạy từ thư mục gốc repo:
    python -m src.utils.sync_local      # (nên chạy trước) lấy bù file còn thiếu từ MinIO
    python -m src.utils.data_stats
"""
import collections
import json

from src.utils.config import Config


def main():
    raw_dir = Config.LOCAL_DATA_DIR / "raw" / "youtube"
    files = list(raw_dir.rglob("*.json"))
    if not files:
        print(f"Không có file nào trong {raw_dir}. Hãy chạy: python -m src.utils.sync_local")
        return

    videos_by_source = collections.defaultdict(set)  # nguồn -> tập video_id
    channels = set()
    rows = collections.Counter()                     # job -> số dòng (item)
    trending_snapshots = 0                           # số lần chụp trending
    total_bytes = 0
    first_time, last_time = None, None

    for path in files:
        total_bytes += path.stat().st_size
        env = json.loads(path.read_text(encoding="utf-8"))
        job = env["job"]
        crawl_time = env.get("crawl_time_utc", "")
        first_time = min(first_time or crawl_time, crawl_time)
        last_time = max(last_time or crawl_time, crawl_time)

        if job == "trending" and env.get("page_index") == 0:
            trending_snapshots += 1  # mỗi lần chụp bắt đầu bằng trang 0

        source = job.split("/")[0]   # "uploads/videos" -> "uploads"
        for item in env["response"].get("items", []):
            rows[job] += 1
            if job.endswith("playlist_items"):
                videos_by_source[source].add(item["contentDetails"]["videoId"])
            elif job in ("trending", "stats") or job.endswith("/videos"):
                videos_by_source[source].add(item["id"])
            elif job in ("channels", "discover/channels"):
                channels.add(item["id"])

    all_videos = set().union(*videos_by_source.values())

    print("=" * 52)
    print(" THỐNG KÊ DỮ LIỆU (bản local data/raw)")
    print("=" * 52)
    print(f" Khoảng thời gian crawl (UTC): {first_time}  ->  {last_time}")
    print(f" Số file raw                : {len(files):,}  ({total_bytes / 1024 / 1024:,.1f} MB)")
    print("-" * 52)
    print(f" VIDEO KHÁC NHAU            : {len(all_videos):,}")
    for source in ("trending", "uploads", "backfill", "stats"):
        if source in videos_by_source:
            print(f"   - xuất hiện trong {source:9s}: {len(videos_by_source[source]):,}")
    print(f" KÊNH ĐÃ TRA CỨU            : {len(channels):,}")
    print(f" SỐ LẦN CHỤP TRENDING       : {trending_snapshots:,}")
    print("-" * 52)
    print(" Số dòng theo job:")
    for job, count in sorted(rows.items()):
        print(f"   {job:28s} {count:>10,}")
    print("=" * 52)


if __name__ == "__main__":
    main()