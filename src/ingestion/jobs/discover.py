"""Job discover: mở rộng danh sách kênh Việt Nam ngoài các kênh từng trending.

Hai nguồn tìm kênh:
  1. search.list (type=channel) theo từ khoá trong configs/discover_keywords.txt
     -> tốn 100 unit/lần, chỉ dùng để TÌM KÊNH; video vẫn lấy qua playlist uploads
        nên nhóm so sánh vẫn công bằng bên trong mỗi kênh.
  2. channelSections.list: đọc mục "kênh nổi bật" (multipleChannels) của các kênh
     đã biết để lan sang kênh liên quan (1 unit/lần).

Kênh tìm được là "ứng viên"; chỉ sau khi tra cứu bằng channels.list và xác nhận là
kênh Việt Nam mới được thêm vào state/channels.json (đánh dấu discovered_utc).

THỨ TỰ CÁC BƯỚC (quan trọng):
  A. Tra cứu các ứng viên còn tồn từ lần trước     (rẻ: 1 unit / 50 kênh)
  B. Đọc mục "kênh nổi bật" của kênh chưa đọc      (1 unit / kênh)
  C. Search theo từ khoá                            (đắt: 100 unit / lần)
  D. Tra cứu các ứng viên vừa tìm được              (rẻ)
Bước B và C chỉ chạy khi còn dư ngân sách, luôn chừa LOOKUP_RESERVE_UNITS cho bước D,
nên kênh tìm được luôn được thêm vào trước khi hết quota.

- Raw:   raw/youtube/discover/{search,sections,channels}/...
- State: state/discover.json (từ khoá đã tìm, kênh đã đọc mục nổi bật, kênh đã loại,
         ứng viên chưa tra cứu); state/channels.json (thêm kênh Việt Nam mới)

Chạy nhiều lần sẽ tiếp tục từ chỗ dừng. Tần suất đề xuất: 1 lần/ngày cho đến khi
đạt TARGET_CHANNELS.
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
# Quota luôn chừa lại cho bước tra cứu ứng viên (200 unit tra được ~10.000 kênh)
LOOKUP_RESERVE_UNITS = 200
# Đã đọc mục "kênh nổi bật" của bấy nhiêu kênh mà không ra ứng viên nào -> ngừng dùng nguồn này
SECTIONS_GIVE_UP_AFTER = 200

SEARCH_COST = 100


def budget_left(yt):
    """Số unit job này còn được dùng hôm nay (vô hạn nếu không có ngân sách)."""
    tracker, limit = getattr(yt, "tracker", None), getattr(yt, "limit", None)
    if tracker is None or limit is None:
        return float("inf")
    return limit - tracker.used_today


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
        self.counts = {}

    def next(self, job):
        value = self.counts.get(job, 0)
        self.counts[job] = value + 1
        return value

    def total(self):
        return sum(self.counts.values())


class _Context:
    """Gom các thứ mọi bước đều cần, để hàm con gọn hơn."""

    def __init__(self, yt, storage, config, run_time):
        self.yt, self.storage, self.config, self.run_time = yt, storage, config, run_time
        self.now_text = fmt_utc(run_time)
        self.pages = _PageCounter()
        self.channels_state = storage.get_json_or_default(STATE_CHANNELS, {"channels": {}})
        self.known = self.channels_state["channels"]
        self.state = storage.get_json_or_default(STATE_DISCOVER, {})
        self.rejected = self.state.setdefault("rejected_channels", {})
        self.pending = set(self.state.get("pending_candidates", []))
        self.added = 0

    def save(self):
        """Lưu cả hai file state (gọi thường xuyên để lỗi giữa chừng không mất tiến độ)."""
        self.state["pending_candidates"] = sorted(self.pending)
        self.state["updated_at_utc"] = self.now_text
        self.channels_state["updated_at_utc"] = self.now_text
        self.storage.put_json(STATE_CHANNELS, self.channels_state)
        self.storage.put_json(STATE_DISCOVER, self.state)


def lookup_candidates(ctx, label):
    """Bước A/D: tra cứu ứng viên bằng channels.list, chỉ giữ kênh Việt Nam."""
    todo = sorted(ctx.pending - set(ctx.known) - set(ctx.rejected))
    ctx.pending &= set(todo)  # bỏ ứng viên đã biết/đã loại
    if not todo:
        return

    added_before = ctx.added
    for batch in chunks(todo):
        params = {"part": CHANNEL_PARTS, "id": ",".join(batch), "maxResults": 50}
        response = ctx.yt.call("channels", "list", **params)
        save_raw(ctx.storage, ctx.config, ctx.run_time, JOB_CHANNELS, "channels.list",
                 params, ctx.pages.next(JOB_CHANNELS), response)

        returned = set()
        for item in response.get("items", []):
            returned.add(item["id"])
            playlist_id = item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
            if playlist_id and is_vietnam_channel(item, ctx.config.REGION_CODE):
                ctx.known[item["id"]] = {"uploads_playlist": playlist_id,
                                         "discovered_utc": ctx.now_text}
                ctx.added += 1
            else:
                ctx.rejected[item["id"]] = ctx.now_text
        for missing in set(batch) - returned:  # kênh đã xoá/không tồn tại
            ctx.rejected[missing] = ctx.now_text

        ctx.pending -= set(batch)
        ctx.save()  # lưu sau mỗi lô: kênh đã thêm không bao giờ bị mất

    logger.info("Tra cứu %s: %d ứng viên -> thêm %d kênh Việt Nam (state có %d kênh)",
                label, len(todo), ctx.added - added_before, len(ctx.known))


def featured_channels(ctx):
    """Bước B: đọc mục 'kênh nổi bật' của các kênh đã biết mà chưa đọc lần nào."""
    checked = ctx.state.setdefault("sections_checked", {})
    found_total = ctx.state.get("sections_found_total", 0)
    if len(checked) >= SECTIONS_GIVE_UP_AFTER and found_total == 0:
        logger.info("Sections: đã đọc %d kênh mà không có ứng viên nào -> bỏ qua nguồn này", len(checked))
        return
    todo = [cid for cid in sorted(ctx.known) if cid not in checked][:MAX_SECTION_CALLS_PER_RUN]
    found, done = set(), 0

    for channel_id in todo:
        if budget_left(ctx.yt) < 1 + LOOKUP_RESERVE_UNITS:
            logger.info("Sections: dừng sớm để chừa quota cho bước tra cứu")
            break
        params = {"part": CHANNEL_SECTION_PARTS, "channelId": channel_id}
        response = ctx.yt.call("channelSections", "list", **params)
        save_raw(ctx.storage, ctx.config, ctx.run_time, JOB_SECTIONS, "channelSections.list",
                 params, ctx.pages.next(JOB_SECTIONS), response)
        checked[channel_id] = ctx.now_text
        done += 1

        for section in response.get("items", []):
            if section.get("snippet", {}).get("type") == "multipleChannels":
                ids = section.get("contentDetails", {}).get("channels", [])
                found.update(ids)
                ctx.pending.update(ids)
                ctx.state["sections_found_total"] = ctx.state.get("sections_found_total", 0) + len(ids)

        if done % 100 == 0:
            ctx.save()
        if len(checked) >= SECTIONS_GIVE_UP_AFTER and ctx.state.get("sections_found_total", 0) == 0:
            logger.info("Sections: %d kênh không có ứng viên nào -> ngừng dùng nguồn này", len(checked))
            break

    ctx.save()
    logger.info("Sections: đọc %d kênh, %d kênh ứng viên", done, len(found))


def search_channels(ctx):
    """Bước C: tìm kênh theo từ khoá, chỉ khi còn đủ quota (luôn chừa phần cho bước D)."""
    done_keywords = ctx.state.setdefault("searched_keywords", {})
    target_left = TARGET_CHANNELS - len(ctx.known)
    found, calls, stop_reason = set(), 0, None

    for keyword in load_keywords(ctx.config):
        if keyword in done_keywords:
            continue
        if calls >= MAX_SEARCH_CALLS_PER_RUN:
            stop_reason = f"đủ {MAX_SEARCH_CALLS_PER_RUN} lần search/lượt"
            break
        if len(found) >= target_left:
            stop_reason = "đủ ứng viên cho mục tiêu"
            break
        # Cần đủ quota cho TOÀN BỘ từ khoá, để không bỏ dở giữa chừng
        if budget_left(ctx.yt) < SEARCH_COST * SEARCH_PAGES_PER_KEYWORD + LOOKUP_RESERVE_UNITS:
            stop_reason = "chừa quota cho bước tra cứu"
            break

        page_token = None
        for _ in range(SEARCH_PAGES_PER_KEYWORD):
            params = {
                "part": SEARCH_PARTS, "type": "channel", "q": keyword,
                "regionCode": ctx.config.REGION_CODE, "relevanceLanguage": "vi", "maxResults": 50,
            }
            if page_token:
                params["pageToken"] = page_token
            response = ctx.yt.call("search", "list", **params)
            save_raw(ctx.storage, ctx.config, ctx.run_time, JOB_SEARCH, "search.list",
                     params, ctx.pages.next(JOB_SEARCH), response)
            calls += 1

            for item in response.get("items", []):
                channel_id = item.get("id", {}).get("channelId")
                if channel_id:
                    found.add(channel_id)
                    ctx.pending.add(channel_id)

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        done_keywords[keyword] = ctx.now_text
        ctx.save()  # lưu sau mỗi từ khoá: không tìm lại, ứng viên không mất
        logger.info("Từ khoá '%s': tổng cộng %d kênh ứng viên", keyword, len(found))

    logger.info("Search: %d lần gọi (~%d unit), %d kênh ứng viên%s", calls, calls * SEARCH_COST,
                len(found), f" — dừng vì {stop_reason}" if stop_reason else "")


def run(yt, storage, config, run_time):
    ctx = _Context(yt, storage, config, run_time)

    # A. Ứng viên còn tồn từ lần trước (lần trước có thể dừng trước khi kịp tra cứu)
    lookup_candidates(ctx, "ứng viên tồn")

    if len(ctx.known) >= TARGET_CHANNELS:
        logger.info("Đã có %d kênh (mục tiêu %d) -> không tìm thêm", len(ctx.known), TARGET_CHANNELS)
    else:
        # B + C. Gom ứng viên mới, chỉ khi còn dư quota
        featured_channels(ctx)
        search_channels(ctx)
        # D. Tra cứu ngay trong lượt này
        lookup_candidates(ctx, "ứng viên mới")

    ctx.save()
    logger.info("Discover: %d file raw, thêm %d kênh Việt Nam, state có %d/%d kênh, còn %d ứng viên chờ",
                ctx.pages.total(), ctx.added, len(ctx.known), TARGET_CHANNELS, len(ctx.pending))
    return ctx.pages.total()