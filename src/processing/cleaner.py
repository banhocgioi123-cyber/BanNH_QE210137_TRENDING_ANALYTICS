"""Tầng Processing: đọc raw JSON từ MinIO, làm sạch rồi nạp vào PostgreSQL.

Luồng: MinIO (raw/youtube/...) -> parse envelope theo job -> làm sạch -> upsert theo lô vào Postgres.

Chạy từ thư mục gốc repo:
    python -m src.processing.cleaner                       # đọc từ MinIO (mặc định)
    python -m src.processing.cleaner --source local        # đọc bản sao data/raw (nhanh hơn)
    python -m src.processing.cleaner --prefix raw/youtube/trending/
    python -m src.processing.cleaner --recent-days 2         # chỉ xét 2 ngày gần nhất (lịch tự động)

Chạy lại bao nhiêu lần cũng an toàn: file đã có trong bảng raw_files sẽ bị bỏ qua,
mọi lệnh ghi đều dùng ON CONFLICT. Mỗi lô file được ghi trong MỘT transaction
(dữ liệu + raw_files), nên lỗi giữa chừng không để lại lô dở dang.

Làm sạch:
  - thời gian ISO 8601 -> TIMESTAMPTZ; thời lượng 'PT1H2M3S' -> giây
  - số đếm dạng chuỗi -> BIGINT; video ẩn like/comment -> NULL
  - captured_at lấy từ tên object (dt=<ngày>/<crawler>_<HHMMSS>_pNN.json)
  - channels/videos giữ bản mới nhất theo captured_at, first_seen_at giữ mốc sớm nhất
"""
import argparse
import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2.extras import execute_values

from src.utils.config import Config

logger = logging.getLogger(__name__)

DB_CONFIG = json.loads((Config.REPO_ROOT / "configs" / "db_config.json").read_text(encoding="utf-8"))

KEY_PATTERN = re.compile(
    r"^raw/youtube/(?P<job>.+)/dt=(?P<date>\d{4}-\d{2}-\d{2})/"
    r"(?P<crawler>.+)_(?P<hms>\d{6})_p(?P<page>\d+)\.json$"
)
DURATION_PATTERN = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")

VIDEO_JOBS = {"trending", "trending_category", "stats", "uploads/videos", "backfill/videos"}
CHANNEL_JOBS = {"channels", "discover/channels"}
PLAYLIST_JOBS = {"uploads/playlist_items", "backfill/playlist_items"}

# Câu lệnh ghi cho từng bảng.
# channels/videos: chỉ cập nhật khi bản mới chụp muộn hơn bản đang có.
UPSERT_SQL = {
    "categories": """
        INSERT INTO categories (category_id, title, assignable) VALUES %s
        ON CONFLICT (category_id) DO UPDATE SET title = EXCLUDED.title, assignable = EXCLUDED.assignable
    """,
    "channels": """
        INSERT INTO channels (channel_id, title, custom_url, country, default_language, published_at,
            subscriber_count, hidden_subscriber, video_count, view_count, uploads_playlist,
            first_source_job, first_seen_at, last_seen_at) VALUES %s
        ON CONFLICT (channel_id) DO UPDATE SET
            title = CASE WHEN EXCLUDED.last_seen_at >= channels.last_seen_at THEN EXCLUDED.title ELSE channels.title END,
            custom_url = CASE WHEN EXCLUDED.last_seen_at >= channels.last_seen_at THEN EXCLUDED.custom_url ELSE channels.custom_url END,
            country = CASE WHEN EXCLUDED.last_seen_at >= channels.last_seen_at THEN EXCLUDED.country ELSE channels.country END,
            default_language = CASE WHEN EXCLUDED.last_seen_at >= channels.last_seen_at THEN EXCLUDED.default_language ELSE channels.default_language END,
            published_at = COALESCE(channels.published_at, EXCLUDED.published_at),
            subscriber_count = CASE WHEN EXCLUDED.last_seen_at >= channels.last_seen_at THEN EXCLUDED.subscriber_count ELSE channels.subscriber_count END,
            hidden_subscriber = CASE WHEN EXCLUDED.last_seen_at >= channels.last_seen_at THEN EXCLUDED.hidden_subscriber ELSE channels.hidden_subscriber END,
            video_count = CASE WHEN EXCLUDED.last_seen_at >= channels.last_seen_at THEN EXCLUDED.video_count ELSE channels.video_count END,
            view_count = CASE WHEN EXCLUDED.last_seen_at >= channels.last_seen_at THEN EXCLUDED.view_count ELSE channels.view_count END,
            uploads_playlist = COALESCE(EXCLUDED.uploads_playlist, channels.uploads_playlist),
            first_source_job = CASE WHEN EXCLUDED.first_seen_at < channels.first_seen_at THEN EXCLUDED.first_source_job ELSE channels.first_source_job END,
            first_seen_at = LEAST(channels.first_seen_at, EXCLUDED.first_seen_at),
            last_seen_at = GREATEST(channels.last_seen_at, EXCLUDED.last_seen_at),
            is_stub = false
    """,
    # Dòng tạm để khoá ngoại videos -> channels/categories luôn hợp lệ (xem configs/schema.sql)
    "channel_stubs": """
        INSERT INTO channels (channel_id, is_stub, first_source_job, first_seen_at, last_seen_at)
        SELECT id, true, 'stub', 'infinity'::TIMESTAMPTZ, '-infinity'::TIMESTAMPTZ FROM (VALUES %s) AS t(id)
        ON CONFLICT (channel_id) DO NOTHING
    """,
    "category_stubs": """
        INSERT INTO categories (category_id) SELECT id FROM (VALUES %s) AS t(id)
        ON CONFLICT (category_id) DO NOTHING
    """,
    "videos": """
        INSERT INTO videos (video_id, channel_id, published_at, title, description, tags, category_id,
            default_language, default_audio_language, duration_s, definition, caption,
            live_broadcast_content, actual_start_time, scheduled_start_time,
            first_source_job, first_seen_at, last_seen_at) VALUES %s
        ON CONFLICT (video_id) DO UPDATE SET
            channel_id = COALESCE(videos.channel_id, EXCLUDED.channel_id),
            published_at = CASE WHEN EXCLUDED.last_seen_at >= videos.last_seen_at THEN EXCLUDED.published_at ELSE videos.published_at END,
            title = CASE WHEN EXCLUDED.last_seen_at >= videos.last_seen_at THEN EXCLUDED.title ELSE videos.title END,
            description = CASE WHEN EXCLUDED.last_seen_at >= videos.last_seen_at THEN EXCLUDED.description ELSE videos.description END,
            tags = CASE WHEN EXCLUDED.last_seen_at >= videos.last_seen_at THEN EXCLUDED.tags ELSE videos.tags END,
            category_id = CASE WHEN EXCLUDED.last_seen_at >= videos.last_seen_at THEN EXCLUDED.category_id ELSE videos.category_id END,
            default_language = CASE WHEN EXCLUDED.last_seen_at >= videos.last_seen_at THEN EXCLUDED.default_language ELSE videos.default_language END,
            default_audio_language = CASE WHEN EXCLUDED.last_seen_at >= videos.last_seen_at THEN EXCLUDED.default_audio_language ELSE videos.default_audio_language END,
            duration_s = CASE WHEN EXCLUDED.last_seen_at >= videos.last_seen_at THEN EXCLUDED.duration_s ELSE videos.duration_s END,
            definition = CASE WHEN EXCLUDED.last_seen_at >= videos.last_seen_at THEN EXCLUDED.definition ELSE videos.definition END,
            caption = CASE WHEN EXCLUDED.last_seen_at >= videos.last_seen_at THEN EXCLUDED.caption ELSE videos.caption END,
            live_broadcast_content = CASE WHEN EXCLUDED.last_seen_at >= videos.last_seen_at THEN EXCLUDED.live_broadcast_content ELSE videos.live_broadcast_content END,
            actual_start_time = COALESCE(EXCLUDED.actual_start_time, videos.actual_start_time),
            scheduled_start_time = COALESCE(EXCLUDED.scheduled_start_time, videos.scheduled_start_time),
            first_source_job = CASE WHEN EXCLUDED.first_seen_at < videos.first_seen_at THEN EXCLUDED.first_source_job ELSE videos.first_source_job END,
            first_seen_at = LEAST(videos.first_seen_at, EXCLUDED.first_seen_at),
            last_seen_at = GREATEST(videos.last_seen_at, EXCLUDED.last_seen_at)
    """,
    "video_sources": """
        INSERT INTO video_sources (video_id, source_job, first_captured_at) VALUES %s
        ON CONFLICT (video_id, source_job) DO UPDATE
            SET first_captured_at = LEAST(video_sources.first_captured_at, EXCLUDED.first_captured_at)
    """,
    "video_stats": """
        INSERT INTO video_stats (video_id, captured_at, source_job, view_count, like_count, comment_count)
        VALUES %s ON CONFLICT DO NOTHING
    """,
    "trending_snapshots": """
        INSERT INTO trending_snapshots (video_id, captured_at, source, category_id, page_index, position)
        VALUES %s ON CONFLICT DO NOTHING
    """,
    "playlist_items": """
        INSERT INTO playlist_items (video_id, playlist_id, video_published_at, captured_at, source_job)
        VALUES %s ON CONFLICT DO NOTHING
    """,
    "discover_candidates": """
        INSERT INTO discover_candidates (channel_id, method, query_or_parent, captured_at)
        VALUES %s ON CONFLICT DO NOTHING
    """,
    "raw_files": """
        INSERT INTO raw_files (object_key, job, endpoint, crawler_id, captured_at, crawl_time_utc, page_index, n_items)
        VALUES %s ON CONFLICT DO NOTHING
    """,
}


# ----------------------------------------------------------------------------
# Hàm làm sạch giá trị
# ----------------------------------------------------------------------------
def parse_time(text):
    """'2026-09-24T01:00:03Z' -> datetime UTC; chuỗi rỗng/thiếu -> None."""
    if not text:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def parse_duration(text):
    """ISO 8601 'P1DT2H3M4S' -> số giây; livestream chưa kết thúc ('P0D') -> 0; sai định dạng -> None."""
    match = DURATION_PATTERN.match(text or "")
    if not match:
        return None
    days, hours, minutes, seconds = (int(part or 0) for part in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def to_int(value):
    """Số đếm API trả về dạng chuỗi ('12345'); thiếu (bị ẩn) -> None."""
    return int(value) if value not in (None, "") else None


def parse_key(key):
    """Tách job, crawler và mốc chụp từ tên object."""
    match = KEY_PATTERN.match(key)
    if not match:
        return None
    captured_at = datetime.strptime(f"{match['date']} {match['hms']}", "%Y-%m-%d %H%M%S").replace(tzinfo=timezone.utc)
    return {"job": match["job"], "crawler_id": match["crawler"], "captured_at": captured_at}


# ----------------------------------------------------------------------------
# Chuyển một envelope thành các dòng cho từng bảng
# ----------------------------------------------------------------------------
class Batch:
    """Gom dòng của nhiều file rồi ghi một lần. Bảng có khoá được khử trùng ngay trong lô
    (Postgres không cho ON CONFLICT DO UPDATE đụng một khoá hai lần trong cùng câu lệnh)."""

    def __init__(self):
        self.keyed = {name: {} for name in ("categories", "channels", "videos", "video_sources")}
        self.rows = {name: {} for name in ("video_stats", "trending_snapshots", "playlist_items",
                                            "discover_candidates", "raw_files")}

    def keep_latest(self, table, key, row, seen_index):
        """Giữ bản chụp muộn nhất trong lô; first_seen/first_source lấy từ bản sớm nhất."""
        old = self.keyed[table].get(key)
        if old is None:
            self.keyed[table][key] = row
            return
        first = min(old, row, key=lambda r: r[seen_index])
        latest = list(max(old, row, key=lambda r: r[seen_index + 1]))
        latest[seen_index - 1] = first[seen_index - 1]  # first_source_job
        latest[seen_index] = first[seen_index]          # first_seen_at
        self.keyed[table][key] = tuple(latest)

    def add_source(self, video_id, job, captured_at):
        old = self.keyed["video_sources"].get((video_id, job))
        if old is None or captured_at < old[2]:
            self.keyed["video_sources"][(video_id, job)] = (video_id, job, captured_at)

    def add_row(self, table, key, row):
        self.rows[table].setdefault(key, row)

    def tables(self):
        for table, rows in {**self.keyed, **self.rows}.items():
            if rows:
                yield table, list(rows.values())


def video_row(item, job, captured_at):
    snippet = item.get("snippet", {})
    details = item.get("contentDetails", {})
    live = item.get("liveStreamingDetails", {})
    return (
        item["id"], snippet.get("channelId"), parse_time(snippet.get("publishedAt")),
        snippet.get("title"), snippet.get("description"), snippet.get("tags"),
        to_int(snippet.get("categoryId")), snippet.get("defaultLanguage"),
        snippet.get("defaultAudioLanguage"), parse_duration(details.get("duration")),
        details.get("definition"),
        {"true": True, "false": False}.get(details.get("caption")),
        snippet.get("liveBroadcastContent"), parse_time(live.get("actualStartTime")),
        parse_time(live.get("scheduledStartTime")), job, captured_at, captured_at,
    )


def channel_row(item, job, captured_at):
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    playlists = item.get("contentDetails", {}).get("relatedPlaylists", {})
    return (
        item["id"], snippet.get("title"), snippet.get("customUrl"), snippet.get("country"),
        snippet.get("defaultLanguage"), parse_time(snippet.get("publishedAt")),
        to_int(stats.get("subscriberCount")), stats.get("hiddenSubscriberCount"),
        to_int(stats.get("videoCount")), to_int(stats.get("viewCount")),
        playlists.get("uploads"), job, captured_at, captured_at,
    )


def add_envelope(batch, key, meta, env):
    """Đưa một file raw vào lô. Trả về số item đã đọc."""
    job, captured_at = meta["job"], meta["captured_at"]
    endpoint = env.get("request", {}).get("endpoint")
    params = env.get("request", {}).get("params", {})
    page_index = env.get("page_index", 0)
    items = (env.get("response") or {}).get("items", [])

    if endpoint == "videoCategories.list":
        for item in items:
            snippet = item.get("snippet", {})
            batch.keyed["categories"][int(item["id"])] = (int(item["id"]), snippet.get("title"), snippet.get("assignable"))

    elif job in VIDEO_JOBS:
        for position, item in enumerate(items):
            video_id = item["id"]
            batch.keep_latest("videos", video_id, video_row(item, job, captured_at), seen_index=16)
            batch.add_source(video_id, job, captured_at)
            stats = item.get("statistics", {})
            batch.add_row("video_stats", (video_id, captured_at, job), (
                video_id, captured_at, job, to_int(stats.get("viewCount")),
                to_int(stats.get("likeCount")), to_int(stats.get("commentCount")),
            ))
            if job in ("trending", "trending_category"):
                source = "main" if job == "trending" else "category"
                category_id = int(params.get("videoCategoryId", 0))
                batch.add_row("trending_snapshots", (video_id, captured_at, source, category_id),
                              (video_id, captured_at, source, category_id, page_index, position))

    elif job in CHANNEL_JOBS:
        for item in items:
            batch.keep_latest("channels", item["id"], channel_row(item, job, captured_at), seen_index=12)

    elif job in PLAYLIST_JOBS:
        playlist_id = params.get("playlistId", "")
        for item in items:
            details = item.get("contentDetails", {})
            video_id = details.get("videoId")
            if not video_id:
                continue
            batch.add_source(video_id, job, captured_at)
            batch.add_row("playlist_items", (video_id, playlist_id, captured_at), (
                video_id, playlist_id, parse_time(details.get("videoPublishedAt")), captured_at, job,
            ))

    elif job == "discover/search":
        query = params.get("q", "")
        for item in items:
            channel_id = item.get("id", {}).get("channelId")
            if channel_id:
                batch.add_row("discover_candidates", (channel_id, "search", query, captured_at),
                              (channel_id, "search", query, captured_at))

    elif job == "discover/sections":
        parent = params.get("channelId", "")
        for section in items:
            if section.get("snippet", {}).get("type") != "multipleChannels":
                continue
            for channel_id in section.get("contentDetails", {}).get("channels", []):
                batch.add_row("discover_candidates", (channel_id, "sections", parent, captured_at),
                              (channel_id, "sections", parent, captured_at))

    batch.add_row("raw_files", key, (
        key, job, endpoint, meta["crawler_id"], captured_at,
        parse_time(env.get("crawl_time_utc")), page_index, len(items),
    ))
    return len(items)


# ----------------------------------------------------------------------------
# Nguồn đọc: MinIO (bản chính) hoặc bản sao local
# ----------------------------------------------------------------------------
class MinioSource:
    name = "MinIO"

    def __init__(self):
        from src.utils.minio_client import MinioStorage  # chỉ cần thư viện minio khi đọc MinIO
        self.storage = MinioStorage()

    def list_keys(self, prefix):
        return self.storage.list_keys(prefix)

    def read(self, key):
        return self.storage.get_json(key)


class LocalSource:
    name = "local data/raw"

    def list_keys(self, prefix):
        root = Config.LOCAL_DATA_DIR
        return sorted(path.relative_to(root).as_posix() for path in (root / prefix).rglob("*.json"))

    def read(self, key):
        return json.loads((Config.LOCAL_DATA_DIR / key).read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------
# Kết nối DB và nạp
# ----------------------------------------------------------------------------
def connect():
    return psycopg2.connect(
        host=Config.POSTGRES_HOST or DB_CONFIG["host"],
        port=int(Config.POSTGRES_PORT or DB_CONFIG["port"]),
        dbname=Config.POSTGRES_DB or DB_CONFIG["database"],
        user=Config.POSTGRES_USER,
        password=Config.POSTGRES_PASSWORD,
    )


def apply_sql_files(conn):
    """Tạo bảng (schema.sql) và view (labels.sql). Cả hai file chạy lại an toàn."""
    with conn.cursor() as cur:
        for relative in DB_CONFIG["sql_files"]:
            cur.execute((Config.REPO_ROOT / relative).read_text(encoding="utf-8"))
    conn.commit()


def write_batch(conn, batch):
    """Ghi một lô trong một transaction; raw_files ghi cuối để chỉ đánh dấu khi dữ liệu đã vào.
    Thứ tự bảng (categories -> channels -> videos -> bảng con) theo khoá ngoại."""
    counts = {}
    with conn.cursor() as cur:
        for table, rows in batch.tables():
            if table == "raw_files":
                continue
            if table == "videos":
                # Kênh/danh mục chưa có thì chèn dòng tạm trước, để khoá ngoại không chặn video
                channel_ids = {(row[1],) for row in rows if row[1]}
                category_ids = {(row[6],) for row in rows if row[6] is not None}
                execute_values(cur, UPSERT_SQL["channel_stubs"], list(channel_ids), page_size=1000)
                execute_values(cur, UPSERT_SQL["category_stubs"], list(category_ids), page_size=1000)
            execute_values(cur, UPSERT_SQL[table], rows, page_size=1000)
            counts[table] = len(rows)
        raw_rows = list(batch.rows["raw_files"].values())
        execute_values(cur, UPSERT_SQL["raw_files"], raw_rows, page_size=1000)
    conn.commit()
    return counts


def list_candidate_keys(source, prefix, recent_days, conn):
    """Liệt kê key cần xét. recent_days=None: quét toàn bộ prefix (chậm, ~3 phút với 165k object).
    recent_days=N: chỉ liệt kê raw/youtube/<job>/dt=<ngày>/ cho từng job đã biết, từ ngày sớm hơn trong hai mốc
    (hôm nay - N) và (ngày của file mới nhất đã nạp - 1) đến hôm nay. Nhờ vậy máy tắt nhiều ngày
    thì lần chạy sau vẫn tự nạp bù, không bỏ sót phân vùng nào."""
    if recent_days is None:
        return source.list_keys(prefix)
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT job FROM raw_files")
        jobs = {row[0] for row in cur.fetchall()}
        cur.execute("SELECT MAX(captured_at) FROM raw_files")
        last_loaded = cur.fetchone()[0]
    jobs |= VIDEO_JOBS | CHANNEL_JOBS | PLAYLIST_JOBS | {"discover/search", "discover/sections"}
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=recent_days)
    if last_loaded is not None:
        start = min(start, last_loaded.date() - timedelta(days=1))
    n_days = (today - start).days
    if n_days > recent_days:
        logger.info("Nạp bù: lần nạp cuối %s -> xét %d ngày gần nhất", last_loaded, n_days + 1)
    keys = []
    for job in sorted(jobs):
        for offset in range(n_days + 1):
            day = today - timedelta(days=offset)
            day_prefix = f"raw/youtube/{job}/dt={day:%Y-%m-%d}/"
            if day_prefix.startswith(prefix):
                keys.extend(source.list_keys(day_prefix))
    return keys


def safe_read(source, key, attempts=3):
    """Đọc một file; lỗi mạng/đọc dở thì thử lại. Vẫn lỗi -> trả None (file không được đánh dấu
    đã nạp, lần chạy sau sẽ thử lại) để một object hỏng không làm dừng cả lượt nạp."""
    for attempt in range(1, attempts + 1):
        try:
            return source.read(key)
        except Exception as error:  # noqa: BLE001 — lỗi S3/mạng/JSON đều xử lý như nhau
            if attempt == attempts:
                logger.warning("Không đọc được %s sau %d lần: %s", key, attempts, error)
                return None
            time.sleep(attempt)


def main():
    parser = argparse.ArgumentParser(description="Nạp raw JSON từ MinIO vào PostgreSQL")
    parser.add_argument("--source", choices=("minio", "local"), default="minio")
    parser.add_argument("--prefix", default="raw/youtube/", help="Chỉ nạp các key bắt đầu bằng prefix này")
    parser.add_argument("--recent-days", type=int, default=None,
                        help="Chỉ liệt kê phân vùng dt= của N ngày gần nhất (nhanh, dùng cho lịch tự động). "
                             "Bỏ trống = quét toàn bộ")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    source = MinioSource() if args.source == "minio" else LocalSource()
    batch_size = DB_CONFIG["load_batch_files"]
    threads = DB_CONFIG["minio_download_threads"]

    conn = connect()
    apply_sql_files(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT object_key FROM raw_files")
        loaded = {row[0] for row in cur.fetchall()}

    keys = [key for key in list_candidate_keys(source, args.prefix, args.recent_days, conn) if key not in loaded]
    logger.info("Nguồn %s: %d file mới cần nạp (đã nạp trước đó: %d)", source.name, len(keys), len(loaded))

    started, done, items, skipped, failed = time.time(), 0, 0, [], []
    totals = {}
    with ThreadPoolExecutor(max_workers=threads) as pool:
        for start in range(0, len(keys), batch_size):
            chunk = keys[start:start + batch_size]
            batch = Batch()
            for key, env in zip(chunk, pool.map(lambda k: safe_read(source, k), chunk)):
                meta = parse_key(key)
                if meta is None:
                    skipped.append(key)  # tên object không theo quy ước tầng raw
                    continue
                if env is None:
                    failed.append(key)
                    continue
                items += add_envelope(batch, key, meta, env)
            for table, count in write_batch(conn, batch).items():
                totals[table] = totals.get(table, 0) + count
            done += len(chunk)
            elapsed = time.time() - started
            logger.info("Đã nạp %d/%d file (%.0f file/giây, %d item)", done, len(keys), done / max(elapsed, 1), items)

    # Cập nhật thống kê cho bộ lập kế hoạch truy vấn sau khi nạp nhiều dữ liệu
    conn.commit()  # đóng transaction của câu SELECT raw_files (ANALYZE phải chạy ngoài transaction)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("ANALYZE")
    conn.close()

    logger.info("Xong sau %.1f phút: %d file, %d item. Dòng gửi vào từng bảng: %s",
                (time.time() - started) / 60, done, items, totals)
    if skipped:
        logger.warning("Bỏ qua %d file sai quy ước tên, ví dụ: %s", len(skipped), skipped[:3])
    if failed:
        logger.warning("%d file đọc lỗi, chưa nạp (chạy lại để thử tiếp): %s", len(failed), failed[:10])


if __name__ == "__main__":
    main()
