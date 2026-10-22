"""
Đếm số video "hoàn chỉnh" trong data/raw: đủ thông tin để thành 1 dòng
trong bảng phân tích (giờ đăng, lượt xem, quy mô kênh).

Đặt file vào src/utils/ rồi chạy từ thư mục gốc repo:
    python -m src.utils.complete_rows
    python -m src.utils.complete_rows --data-dir data/raw
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

VN = timezone(timedelta(hours=7))


def parse_time(s):
    """Đổi chuỗi thời gian ISO của API (đuôi Z) sang datetime có múi giờ."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def is_office_hour(dt_utc):
    """Giờ hành chính: 8:00–17:00, Thứ 2–Thứ 6, theo giờ Việt Nam."""
    t = dt_utc.astimezone(VN)
    return t.weekday() < 5 and 8 <= t.hour < 17


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data/raw")
    args = ap.parse_args()
    root = Path(args.data_dir)

    videos = {}          # video_id -> {published, channel, has_stats}
    subs = {}            # channel_id -> số subscriber (None nếu kênh ẩn)
    trending_ids = set() # video từng xuất hiện trong chart mostPopular
    first_trending = None
    bad_files = 0

    for f in root.rglob("*.json"):
        try:
            with f.open(encoding="utf-8") as fh:
                env = json.load(fh)
        except (OSError, json.JSONDecodeError):
            bad_files += 1
            continue

        resp = env.get("response") or {}
        is_trending = env.get("job") == "trending" or "trending" in f.parts

        # Mốc bắt đầu theo dõi Trending = lần chụp trending sớm nhất
        if is_trending:
            t = parse_time(env.get("crawl_time_utc"))
            if t and (first_trending is None or t < first_trending):
                first_trending = t

        for it in resp.get("items") or []:
            kind = it.get("kind")

            # Item từ videos.list (job trending, stats, */videos)
            if kind == "youtube#video" and isinstance(it.get("id"), str):
                vid = it["id"]
                sn = it.get("snippet") or {}
                st = it.get("statistics") or {}
                v = videos.setdefault(vid, {"published": None, "channel": None, "has_stats": False})
                if sn.get("publishedAt"):
                    v["published"] = parse_time(sn["publishedAt"])
                if sn.get("channelId"):
                    v["channel"] = sn["channelId"]
                if "viewCount" in st:
                    v["has_stats"] = True
                if is_trending:
                    trending_ids.add(vid)

            # Item từ channels.list: lấy số subscriber
            elif kind == "youtube#channel" and isinstance(it.get("id"), str):
                st = it.get("statistics") or {}
                if st.get("hiddenSubscriberCount"):
                    subs.setdefault(it["id"], None)
                elif "subscriberCount" in st:
                    subs[it["id"]] = int(st["subscriberCount"])

    # Lọc dần theo từng điều kiện để thấy bị rơi ở bước nào
    detail = [v for v in videos.values() if v["published"] and v["channel"]]
    with_stats = [v for v in detail if v["has_stats"]]
    hidden = [v for v in with_stats if v["channel"] in subs and subs[v["channel"]] is None]
    complete_ids = [vid for vid, v in videos.items()
                    if v["published"] and v["channel"] and v["has_stats"]
                    and subs.get(v["channel"]) is not None]
    complete_trend = [vid for vid in complete_ids if vid in trending_ids]

    # Tập kiểm định: video đăng sau khi bắt đầu theo dõi Trending
    analysis = [vid for vid in complete_ids
                if first_trending and videos[vid]["published"] >= first_trending]
    a_trend = [vid for vid in analysis if vid in trending_ids]
    a_office = [vid for vid in analysis if is_office_hour(videos[vid]["published"])]
    a_office_trend = [vid for vid in a_office if vid in trending_ids]

    line = "=" * 56
    print(line)
    print(" SỐ VIDEO ĐỦ THÔNG TIN THÀNH 1 DÒNG HOÀN CHỈNH")
    print(line)
    print(f" Video có trong videos.list          : {len(videos):,}")
    print(f"  + có publishedAt và channelId      : {len(detail):,}")
    print(f"  + có lượt xem (statistics)         : {len(with_stats):,}")
    print(f"  + kênh có số subscriber            : {len(complete_ids):,}   <- DÒNG HOÀN CHỈNH")
    print(f"    (bị loại vì kênh ẩn subscriber   : {len(hidden):,})")
    print(f"    trong đó từng lọt Trending       : {len(complete_trend):,} / {len(trending_ids):,} video trending")
    print("-" * 56)
    start = first_trending.astimezone(VN).strftime("%d/%m/%Y %H:%M") if first_trending else "?"
    print(f" TẬP KIỂM ĐỊNH (đăng từ {start} giờ VN)")
    print(f"  Dòng hoàn chỉnh                    : {len(analysis):,}")
    print(f"  Lọt Trending                       : {len(a_trend):,}")
    print(f"  Giờ hành chính / giờ nghỉ          : {len(a_office):,} / {len(analysis) - len(a_office):,}")
    print(f"  Trending: hành chính / giờ nghỉ    : {len(a_office_trend):,} / {len(a_trend) - len(a_office_trend):,}")
    if bad_files:
        print(f"\n Bỏ qua {bad_files} file không đọc được")
    print(line)


if __name__ == "__main__":
    main()