import glob
import json
import os
import pandas as pd


def clean_trending():
    print("\n--- Đang xử lý Job: Trending ---")
    files = glob.glob(
        "data/raw/youtube/trending/**/*.json", recursive=True
    ) + glob.glob("data/raw/youtube/backfill/**/trending/**/*.json", recursive=True)

    if not files:
        print("⚠️ Không tìm thấy file JSON nào cho Trending.")
        return

    print(f"📁 Tìm thấy {len(files)} file. Đang phân tích...")
    records = []
    for f in files:
        with open(f, "r", encoding="utf-8") as file:
            try:
                raw_data = json.load(file)
                container = raw_data.get("response", raw_data)
                items = container.get("items", []) if isinstance(container, dict) else (container if isinstance(container, list) else [])
                if not items and isinstance(container, dict) and "id" in container:
                    items = [container]

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    snippet = item.get("snippet", {})
                    stats = item.get("statistics", {})
                    vid = item.get("id") or item.get("video_id")
                    if vid:
                        records.append({
                            "video_id": vid,
                            "title": snippet.get("title"),
                            "channel_id": snippet.get("channelId"),
                            "channel_title": snippet.get("channelTitle"),
                            "published_at": snippet.get("publishedAt"),
                            "view_count": int(stats.get("viewCount", 0) or 0),
                            "like_count": int(stats.get("likeCount", 0) or 0),
                            "comment_count": int(stats.get("commentCount", 0) or 0),
                        })
            except Exception:
                continue

    if records:
        df = pd.DataFrame(records).drop_duplicates(subset=["video_id"])
        os.makedirs("data/processed", exist_ok=True)
        df.to_csv("data/processed/cleaned_trending.csv", index=False)
        print(f"✅ Đã xuất cleaned_trending.csv ({len(df)} bản ghi)")
    else:
        print("⚠️ Không trích xuất được dữ liệu hợp lệ cho Trending.")


def clean_channels():
    print("\n--- Đang xử lý Job: Channels ---")
    files = glob.glob(
        "data/raw/youtube/channels/**/*.json", recursive=True
    ) + glob.glob("data/raw/youtube/backfill/**/channels/**/*.json", recursive=True)

    if not files:
        print("⚠️ Không tìm thấy file JSON nào cho Channels.")
        return

    print(f"📁 Tìm thấy {len(files)} file. Đang phân tích...")
    records = []
    for f in files:
        with open(f, "r", encoding="utf-8") as file:
            try:
                raw_data = json.load(file)
                container = raw_data.get("response", raw_data)
                items = container.get("items", []) if isinstance(container, dict) else (container if isinstance(container, list) else [])
                if not items and isinstance(container, dict) and "id" in container:
                    items = [container]

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    snippet = item.get("snippet", {})
                    stats = item.get("statistics", {})
                    cid = item.get("id") or item.get("channel_id")
                    if cid:
                        records.append({
                            "channel_id": cid,
                            "title": snippet.get("title"),
                            "description": snippet.get("description"),
                            "custom_url": snippet.get("customUrl"),
                            "published_at": snippet.get("publishedAt"),
                            "country": snippet.get("country"),
                            "view_count": int(stats.get("viewCount", 0) or 0),
                            "subscriber_count": int(stats.get("subscriberCount", 0) or 0),
                            "video_count": int(stats.get("videoCount", 0) or 0),
                        })
            except Exception:
                continue

    if records:
        df = pd.DataFrame(records).drop_duplicates(subset=["channel_id"])
        os.makedirs("data/processed", exist_ok=True)
        df.to_csv("data/processed/cleaned_channels.csv", index=False)
        print(f"✅ Đã xuất cleaned_channels.csv ({len(df)} bản ghi)")
    else:
        print("⚠️ Không trích xuất được dữ liệu hợp lệ cho Channels.")


def clean_videos():
    print("\n--- Đang xử lý Job: Videos ---")
    files = (
        glob.glob("data/raw/youtube/videos/**/*.json", recursive=True)
        + glob.glob("data/raw/youtube/uploads/**/*.json", recursive=True)
        + glob.glob("data/raw/youtube/backfill/**/videos/**/*.json", recursive=True)
        + glob.glob("data/raw/youtube/backfill/**/uploads/**/*.json", recursive=True)
    )

    if not files:
        print("⚠️ Không tìm thấy file JSON nào cho Videos.")
        return

    print(f"📁 Tìm thấy {len(files)} file. Đang phân tích...")
    records = []
    for f in files:
        with open(f, "r", encoding="utf-8") as file:
            try:
                raw_data = json.load(file)
                container = raw_data.get("response", raw_data)
                items = container.get("items", []) if isinstance(container, dict) else (container if isinstance(container, list) else [])
                if not items and isinstance(container, dict) and "id" in container:
                    items = [container]

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    snippet = item.get("snippet", {})
                    content_details = item.get("contentDetails", {})
                    vid = item.get("id") or item.get("video_id")
                    if vid:
                        records.append({
                            "video_id": vid,
                            "title": snippet.get("title"),
                            "description": snippet.get("description"),
                            "channel_id": snippet.get("channelId"),
                            "category_id": snippet.get("categoryId"),
                            "published_at": snippet.get("publishedAt"),
                            "duration": content_details.get("duration"),
                            "definition": content_details.get("definition"),
                        })
            except Exception:
                continue

    if records:
        df = pd.DataFrame(records).drop_duplicates(subset=["video_id"])
        os.makedirs("data/processed", exist_ok=True)
        df.to_csv("data/processed/cleaned_videos.csv", index=False)
        print(f"✅ Đã xuất cleaned_videos.csv ({len(df)} bản ghi)")
    else:
        print("⚠️ Không trích xuất được dữ liệu hợp lệ cho Videos.")


def clean_stats():
    print("\n--- Đang xử lý Job: Stats ---")
    files = glob.glob(
        "data/raw/youtube/stats/**/*.json", recursive=True
    ) + glob.glob("data/raw/youtube/backfill/**/stats/**/*.json", recursive=True)

    if not files:
        print("⚠️ Không tìm thấy file JSON nào cho Stats.")
        return

    print(f"📁 Tìm thấy {len(files)} file. Đang phân tích...")
    records = []
    for f in files:
        with open(f, "r", encoding="utf-8") as file:
            try:
                raw_data = json.load(file)
                container = raw_data.get("response", raw_data)
                items = container.get("items", []) if isinstance(container, dict) else (container if isinstance(container, list) else [])
                if not items and isinstance(container, dict) and "id" in container:
                    items = [container]

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    stats = item.get("statistics", {})
                    vid = item.get("id") or item.get("video_id")
                    if vid:
                        records.append({
                            "video_id": vid,
                            "view_count": int(stats.get("viewCount", 0) or 0),
                            "like_count": int(stats.get("likeCount", 0) or 0),
                            "comment_count": int(stats.get("commentCount", 0) or 0),
                        })
            except Exception:
                continue

    if records:
        df = pd.DataFrame(records).drop_duplicates(subset=["video_id"])
        os.makedirs("data/processed", exist_ok=True)
        df.to_csv("data/processed/cleaned_stats.csv", index=False)
        print(f"✅ Đã xuất cleaned_stats.csv ({len(df)} bản ghi)")
    else:
        print("⚠️ Không trích xuất được dữ liệu hợp lệ cho Stats.")


def clean_playlist_items():
    print("\n--- Đang xử lý Job: Playlist Items ---")
    files = glob.glob(
        "data/raw/youtube/playlist_items/**/*.json", recursive=True
    ) + glob.glob("data/raw/youtube/backfill/**/playlist_items/**/*.json", recursive=True)

    if not files:
        print("⚠️ Không tìm thấy file JSON nào cho Playlist Items.")
        return

    print(f"📁 Tìm thấy {len(files)} file. Đang phân tích...")
    records = []
    for f in files:
        with open(f, "r", encoding="utf-8") as file:
            try:
                raw_data = json.load(file)
                container = raw_data.get("response", raw_data)
                items = container.get("items", []) if isinstance(container, dict) else (container if isinstance(container, list) else [])
                if not items and isinstance(container, dict) and "id" in container:
                    items = [container]

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    snippet = item.get("snippet", {})
                    resource = snippet.get("resourceId", {})
                    pid = item.get("id") or item.get("playlist_item_id")
                    if pid:
                        records.append({
                            "playlist_item_id": pid,
                            "playlist_id": snippet.get("playlistId"),
                            "video_id": resource.get("videoId"),
                            "title": snippet.get("title"),
                            "channel_id": snippet.get("channelId"),
                            "published_at": snippet.get("publishedAt"),
                            "position": snippet.get("position"),
                        })
            except Exception:
                continue

    if records:
        df = pd.DataFrame(records).drop_duplicates(subset=["playlist_item_id"])
        os.makedirs("data/processed", exist_ok=True)
        df.to_csv("data/processed/cleaned_playlist_items.csv", index=False)
        print(f"✅ Đã xuất cleaned_playlist_items.csv ({len(df)} bản ghi)")
    else:
        print("⚠️ Không trích xuất được dữ liệu hợp lệ cho Playlist Items.")


import re


def is_vietnamese(text):
  if not text:
    return False

  # 1. Kiểm tra ký tự có dấu đặc trưng của tiếng Việt
  vn_chars = re.compile(
      r"[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ"
      r"ÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴĐ]",
      re.IGNORECASE,
  )
  if vn_chars.search(text):
    return True

  # 2. Kiểm tra các từ khóa/thuật ngữ tiếng Việt không dấu hay xuất hiện
  text_lower = text.lower()
  vn_keywords = [
      "vlog",
      "vlogs",
      "minecraft",
      "kenh",
      "truyen hinh",
      "da bong",
      "free fire",
      "tieng viet",
      "tap",
  ]
  for kw in vn_keywords:
    if re.search(r"\b" + kw + r"\b", text_lower):
      return True

  return False


def clean_discover():
  print("\n--- Đang xử lý Job: Discover (Đã lọc nâng cao tiếng Việt) ---")
  files = glob.glob(
      "data/raw/youtube/discover/**/*.json", recursive=True
  ) + glob.glob("data/raw/youtube/backfill/**/discover/**/*.json", recursive=True)

  if not files:
    print("⚠️ Không tìm thấy file JSON nào cho Discover.")
    return

  print(f"📁 Tìm thấy {len(files)} file. Đang phân tích và lọc sâu...")
  records = []
  filtered_count = 0

  for f in files:
    with open(f, "r", encoding="utf-8") as file:
      try:
        raw_data = json.load(file)
        container = raw_data.get("response", raw_data)
        items = (
            container.get("items", [])
            if isinstance(container, dict)
            else (container if isinstance(container, list) else [])
        )
        if not items and isinstance(container, dict) and "id" in container:
          items = [container]

        for item in items:
          if not isinstance(item, dict):
            continue
          id_info = item.get("id", {})
          snippet = item.get("snippet", {})

          title = snippet.get("title", "")
          channel_title = snippet.get("channelTitle", "")

          # Loại bỏ nếu phát hiện tiếng Việt có dấu hoặc không dấu
          if is_vietnamese(title) or is_vietnamese(channel_title):
            filtered_count += 1
            continue

          vid = (
              id_info.get("videoId")
              if isinstance(id_info, dict)
              else id_info or item.get("video_id")
          )
          if vid:
            records.append({
                "video_id": vid,
                "title": title,
                "channel_id": snippet.get("channelId"),
                "channel_title": channel_title,
                "published_at": snippet.get("publishedAt"),
                "live_broadcast_content": snippet.get(
                    "liveBroadcastContent"
                ),
            })
      except Exception:
        continue

  if records:
    df = (
        pd.DataFrame(records)
        .dropna(subset=["video_id"])
        .drop_duplicates(subset=["video_id"])
    )
    os.makedirs("data/processed", exist_ok=True)
    df.to_csv("data/processed/cleaned_discover.csv", index=False)
    print(
        f"✅ Đã xuất cleaned_discover.csv ({len(df)} bản ghi, đã lọc bỏ"
        f" {filtered_count} bản ghi tiếng Việt cả có dấu và không dấu)"
    )
  else:
    print("⚠️ Không trích xuất được dữ liệu hợp lệ cho Discover.")


if __name__ == "__main__":
    os.makedirs("data/processed", exist_ok=True)
    
    # Thực thi tuần tự đủ 6 jobs
    clean_trending()
    clean_channels()
    clean_videos()
    clean_stats()
    clean_playlist_items()
    clean_discover()

    print("\n🎉 Hoàn thành làm sạch toàn bộ 6 jobs!")