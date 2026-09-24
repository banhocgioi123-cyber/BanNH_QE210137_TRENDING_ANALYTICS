"""Job discover: mở rộng danh sách kênh Việt Nam ngoài các kênh từng trending.

Hai nguồn tìm kênh:
  1. search.list (type=channel) theo từ khoá trong configs/discover_keywords.txt
     -> tốn 100 unit/lần, chỉ dùng để TÌM KÊNH; video vẫn lấy qua playlist uploads
        nên nhóm so sánh vẫn công bằng bên trong mỗi kênh.
  2. channelSections.list: đọc mục "kênh nổi bật" (multipleChannels) của các kênh
     đã biết để lan sang kênh liên quan (1 unit/lần).

Kênh mới được tra bằng channels.list; chỉ kênh Việt Nam mới được thêm vào
state/channels.json (đánh dấu discovered_utc -> job uploads luôn quét).

- Raw:   raw/youtube/discover/{search,sections,channels}/...
- State: state/discover.json (từ khoá đã tìm, kênh đã đọc mục nổi bật, kênh đã loại)
         state/channels.json (thêm kênh Việt Nam mới)

Chạy nhiều lần sẽ tiếp tục từ chỗ dừng. Tần suất đề xuất: 1 lần/ngày,
sau job channels và trước job uploads, cho đến khi đạt TARGET_CHANNELS.
"""
import logging

from src.ingestion.jobs._helpers import (
    STATE_CHANNELS, STATE_DISCOVER, chunks, fmt_utc, save_raw,
)
from src.ingestion.parts import CHANNEL_PARTS, CHANNEL_SECTION_PARTS, SEARCH_PARTS

logger = logging.getLogger(__name__)

JOB_SEARCH = "discover/search"
JOB_SECTIONS = "discover/sections"
JOB_CHANNELS = "discover/channels"

# Dừng tìm kênh mới khi state đã có đủ số kênh này
TARGET_CHANNELS = 2500
# Mỗi từ khoá lấy tối đa bao nhiêu trang (50 kênh/trang, 100 unit/trang)
SEARCH_PAGES_PER_KEYWORD = 3
# Giới hạn số lần gọi search mỗi lần chạy (60 x 100 = 6.000 unit), phần còn lại để hôm sau
MAX_SEARCH_CALLS_PER_RUN = 60
# Giới hạn số kênh đọc mục "kênh nổi bật" mỗi lần chạy (1 unit/kênh)
MAX_SECTION_CALLS_PER_RUN = 1000


def load_keywords(config):
    """Đọc từ khoá, bỏ dòng trống và dòng chú thích."""
    path = config.REPO_ROOT / "configs" / "discover_keywords.txt"
    if not path.exists():
        logger.warning("Không có file %s -> bỏ qua bước search", path)
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def is_vietnam_channel(item, region_code):
    """Kênh Việt Nam: country = VN, hoặc không khai báo country nhưng ngôn ngữ mặc định là tiếng Việt."""
    snippet = item.get("snippet", {})
    country = snippet.get("country")
    if country:
        return country == region_code
    return (snippet.get("defaultLanguage") or "").lower().startswith("vi")


class _PageCounter:
    """Đánh số trang tiếp nối cho từng nhóm raw trong một lần chạy (tránh trùng tên file)."""

    def __init__(self):
        self._next = {}

    def next(self, job):
        value = self._next.get(job, 0)
        self._next[job] = value + 1
        return value


def _checkpoint(storage, state, pending):
    """Lưu tiến độ + kênh ứng viên chưa xử lý, để lần chạy sau tiếp tục được."""
    state["pending_candidates"] = sorted(pending)
    storage.put_json(STATE_DISCOVER, state)


def search_channels(yt, storage, config, run_time, state, pages, target_left, pending):
    """Bước 2: tìm kênh theo từ khoá, thêm channelId tìm được vào `pending`."""
    found = set()
    calls = 0
    done = state.setdefault("searched_keywords", {})

    for keyword in load_keywords(config):
        if keyword in done:
            continue
        if calls >= MAX_SEARCH_CALLS_PER_RUN or len(found) >= target_left:
            break

        page_token = None
        for _ in range(SEARCH_PAGES_PER_KEYWORD):
            params = {
                "part": SEARCH_PARTS, "type": "channel", "q": keyword,
                "regionCode": config.REGION_CODE, "relevanceLanguage": "vi", "maxResults": 50,
            }
            if page_token:
                params["pageToken"] = page_token
            response = yt.call("search", "list", **params)
            save_raw(storage, config, run_time, JOB_SEARCH, "search.list",
                     params, pages.next(JOB_SEARCH), response)
            calls += 1

            for item in response.get("items", []):
                channel_id = item.get("id", {}).get("channelId")
                if channel_id:
                    found.add(channel_id)
                    pending.add(channel_id)

            page_token = response.get("nextPageToken")
            if not page_token or calls >= MAX_SEARCH_CALLS_PER_RUN:
                break

        done[keyword] = fmt_utc(run_time)
        # Lưu ngay: nếu hết quota ở từ khoá sau, lần chạy tới không tìm lại từ khoá này
        _checkpoint(storage, state, pending)
        logger.info("Từ khoá '%s': tổng cộng %d kênh ứng viên", keyword, len(found))

    logger.info("Search: %d lần gọi (~%d unit), %d kênh ứng viên", calls, calls * 100, len(found))


def featured_channels(yt, storage, config, run_time, state, known, pages, pending):
    """Bước 1: đọc mục 'kênh nổi bật' của các kênh đã biết mà chưa đọc lần nào."""
    found = set()
    checked = state.setdefault("sections_checked", {})
    todo = [cid for cid in sorted(known) if cid not in checked][:MAX_SECTION_CALLS_PER_RUN]

    for channel_id in todo:
        params = {"part": CHANNEL_SECTION_PARTS, "channelId": channel_id}
        response = yt.call("channelSections", "list", **params)
        save_raw(storage, config, run_time, JOB_SECTIONS, "channelSections.list",
                 params, pages.next(JOB_SECTIONS), response)
        checked[channel_id] = fmt_utc(run_time)

        for section in response.get("items", []):
            if section.get("snippet", {}).get("type") == "multipleChannels":
                ids = section.get("contentDetails", {}).get("channels", [])
                found.update(ids)
                pending.update(ids)

        if len(checked) % 100 == 0:
            _checkpoint(storage, state, pending)  # lưu định kỳ, phòng lỗi giữa chừng

    _checkpoint(storage, state, pending)
    logger.info("Sections: đọc %d kênh, %d kênh ứng viên", len(todo), len(found))


def run(yt, storage, config, run_time):
    channels_state = storage.get_json_or_default(STATE_CHANNELS, {"channels": {}})
    known = channels_state["channels"]
    state = storage.get_json_or_default(STATE_DISCOVER, {})
    rejected = state.setdefault("rejected_channels", {})
    pages = _PageCounter()
    now_text = fmt_utc(run_time)

    if len(known) >= TARGET_CHANNELS:
        logger.info("Đã có %d kênh (mục tiêu %d) -> không tìm thêm", len(known), TARGET_CHANNELS)
        return 0

    # Ứng viên còn tồn từ lần chạy trước (nếu lần trước bị lỗi giữa chừng)
    pending = set(state.get("pending_candidates", []))

    # Bước 1 + 2: gom ứng viên từ hai nguồn
    featured_channels(yt, storage, config, run_time, state, known, pages, pending)
    target_left = TARGET_CHANNELS - len(known)
    search_channels(yt, storage, config, run_time, state, pages, target_left, pending)

    # Bỏ kênh đã có hoặc đã từng bị loại
    new_ids = sorted(pending - set(known) - set(rejected))
    logger.info("Có %d kênh chưa biết cần kiểm tra", len(new_ids))

    # Bước 3: tra thông tin kênh mới, chỉ giữ kênh Việt Nam
    added = 0
    for batch in chunks(new_ids):
        params = {"part": CHANNEL_PARTS, "id": ",".join(batch), "maxResults": 50}
        response = yt.call("channels", "list", **params)
        save_raw(storage, config, run_time, JOB_CHANNELS, "channels.list",
                 params, pages.next(JOB_CHANNELS), response)

        for item in response.get("items", []):
            playlist_id = item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
            if playlist_id and is_vietnam_channel(item, config.REGION_CODE):
                known[item["id"]] = {"uploads_playlist": playlist_id, "discovered_utc": now_text}
                added += 1
            else:
                rejected[item["id"]] = now_text

    # Ghi state (raw đã lưu ở trên, state chỉ là dữ liệu điều khiển)
    channels_state["updated_at_utc"] = now_text
    state["updated_at_utc"] = now_text
    state["pending_candidates"] = []  # đã xử lý hết ứng viên
    storage.put_json(STATE_CHANNELS, channels_state)
    storage.put_json(STATE_DISCOVER, state)

    total_files = sum(pages._next.values())
    logger.info("Discover: %d file raw, thêm %d kênh Việt Nam, state có %d/%d kênh",
                total_files, added, len(known), TARGET_CHANNELS)
    return total_files
