"""Job channels: lấy thông tin các kênh từng có video trending trong N ngày gần nhất.

- Raw: response của channels.list (subscriber, tuổi kênh, uploads playlist...).
- State: state/channels.json = {channel_id: {uploads_playlist, last_seen_utc}}
  để job uploads biết cần quét playlist nào.

Tần suất đề xuất: 1 lần/ngày, chạy TRƯỚC job uploads.
"""
import logging

from src.ingestion.jobs._helpers import (
    STATE_CHANNELS, chunks, recent_dates, save_raw,
)
from src.ingestion.parts import CHANNEL_PARTS

logger = logging.getLogger(__name__)

JOB_NAME = "channels"

# Gom kênh từ các snapshot trending của bao nhiêu ngày gần nhất
LOOKBACK_DAYS = 7


def collect_trending_channels(storage, run_time):
    """Đọc lại raw trending (chỉ để lấy channelId, KHÔNG sửa raw)."""
    channel_ids = set()
    for day in recent_dates(run_time, LOOKBACK_DAYS):
        for key in storage.list_keys(f"raw/youtube/trending/dt={day}/"):
            envelope = storage.get_json(key)
            for item in envelope["response"].get("items", []):
                channel_id = item.get("snippet", {}).get("channelId")
                if channel_id:
                    channel_ids.add(channel_id)
    return channel_ids


def run(yt, storage, config, run_time):
    channel_ids = collect_trending_channels(storage, run_time)
    if not channel_ids:
        logger.warning("Chưa có dữ liệu trending trong %d ngày gần nhất -> bỏ qua", LOOKBACK_DAYS)
        return 0
    logger.info("Tìm thấy %d kênh từ trending", len(channel_ids))

    # Giữ lại các kênh đã biết từ trước; job uploads tự lọc kênh lâu không xuất hiện
    state = storage.get_json_or_default(STATE_CHANNELS, {"channels": {}})
    known = state["channels"]
    now_text = run_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    saved = 0
    for page_index, batch in enumerate(chunks(sorted(channel_ids))):
        params = {"part": CHANNEL_PARTS, "id": ",".join(batch), "maxResults": 50}
        response = yt.call("channels", "list", **params)
        save_raw(storage, config, run_time, JOB_NAME, "channels.list", params, page_index, response)
        saved += 1

        for item in response.get("items", []):
            playlist_id = item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
            if playlist_id:
                known[item["id"]] = {"uploads_playlist": playlist_id, "last_seen_utc": now_text}

    state["updated_at_utc"] = now_text
    storage.put_json(STATE_CHANNELS, state)
    logger.info("Channels: %d file raw, state có %d kênh", saved, len(known))
    return saved
