# BanNH_QE210137_TRENDING_ANALYTICS

Đồ án môn **ADY201m — Advanced Data Engineering & Science Bootcamp**, FPT University.

**Chủ đề 4: Trending Content (YouTube)**
Câu hỏi nghiên cứu: *Upload video vào khung giờ hành chính hay khung giờ nghỉ ngơi sẽ dễ lọt Top Trending hơn?*

---

## 1. Kiến trúc hệ thống

```
YouTube Data API v3
        │
        ▼
 [1] Ingestion (Python)  ──► lưu JSON thô, không sửa
        │
        ▼
   MinIO (Data Lake)  ──► còn lưu thêm 1 bản ở data/raw/ trên máy
        │
        ▼
 [2] Processing (chưa làm) ──► làm sạch, đổi múi giờ, gắn nhãn trending
        │
        ▼
   PostgreSQL
        │
        ▼
 [3] Phân tích / Model (RStudio, Jupyter) — chưa làm
```

3 container Docker:

| Container | Vai trò |
|---|---|
| `ady201m_minio` | Data Lake, lưu JSON thô. Console: `http://localhost:9001` |
| `ady201m_postgres` | Database sau khi làm sạch |
| `ady201m_pgadmin` | Giao diện quản trị Postgres: `http://localhost:5050` |

Container App (Python/RStudio chạy trong Docker) sẽ bổ sung ở Report 5.

## 2. Yêu cầu trước khi chạy

- Docker Desktop (đang chạy)
- Python 3.11+
- YouTube Data API key ([Google Cloud Console](https://console.cloud.google.com/), bật **YouTube Data API v3**)

## 3. Cài đặt lần đầu

```powershell
git clone <repo-url>
cd BanNH_QE210137_TRENDING_ANALYTICS

# 1. Tạo file .env từ mẫu, rồi điền giá trị thật (KHÔNG commit .env)
copy .env.example .env

# 2. Bật hạ tầng Docker
docker compose up -d
docker compose ps        # cả 3 container phải ở trạng thái "running"

# 3. Cài môi trường Python
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Các biến bắt buộc trong `.env` — xem đầy đủ ở `.env.example`:

| Biến | Ý nghĩa |
|---|---|
| `YOUTUBE_API_KEY` | API key riêng của bạn |
| `CRAWLER_ID` | Định danh máy crawl (chữ thường/số/`_`/`-`), ví dụ `ban` — dùng để gộp dữ liệu nhiều máy mà không đè file |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | Phải khớp với `docker-compose.yml` |
| `MINIO_ENDPOINT` | `localhost:9000` khi chạy trên máy; `minio:9000` khi chạy trong container App |
| `SAVE_LOCAL_COPY` | `true` để crawler ghi thêm bản JSON vào `data/raw/` trên máy |

## 4. Chạy crawler

Luôn chạy bằng `python -m` từ **thư mục gốc repo**.

```powershell
# Lần đầu tiên: chạy đủ 4 job theo đúng thứ tự để khởi tạo dữ liệu
python -m src.ingestion.crawler --job trending channels uploads stats

# Sau đó, lên lịch chạy định kỳ (xem mục 6):
python -m src.ingestion.crawler --job trending stats       # mỗi 3 giờ
python -m src.ingestion.crawler --job channels uploads     # 1 lần/ngày

# Tải dữ liệu đã có trên MinIO về data/raw/ (dùng khi data/raw bị thiếu so với MinIO)
python -m src.utils.sync_local
```

Kết thúc mỗi lần chạy, exit code cho biết kết quả: `0` thành công, `1` lỗi, `2` hết quota. Log chi tiết nằm ở `logs/crawl_<ngày>.log`.

## 5. Các job

| Job | Gọi API | Mục đích | Tần suất |
|---|---|---|---|
| `trending` | `videos.list` (chart=mostPopular) | Nhóm video **có** trending — biến kết quả chính | Mỗi 3 giờ |
| `channels` | `channels.list` | Subscriber, tuổi kênh — biến kiểm soát quy mô kênh | 1 lần/ngày |
| `uploads` | `playlistItems.list` + `videos.list` | Nhóm video **không** trending của cùng các kênh — nhóm so sánh | 1 lần/ngày |
| `stats` | `videos.list` (theo id) | Snapshot view/like/comment theo thời gian — biến kết quả dự phòng | Mỗi 3 giờ |

Nhãn trending/non-trending **không** gắn lúc crawl (một video có thể trending muộn hơn), việc này để cho tầng Processing.

## 6. Lên lịch chạy tự động (Windows Task Scheduler)

Tạo 2 tác vụ, "Start in" trỏ tới thư mục gốc repo, chương trình chạy là `<đường dẫn>\.venv\Scripts\python.exe`:

| Tác vụ | Đối số | Lịch |
|---|---|---|
| Crawl nhanh | `-m src.ingestion.crawler --job trending stats` | 08:00, 11:00, 14:00, 17:00, 20:00, 23:00 |
| Crawl đầy đủ | `-m src.ingestion.crawler --job channels uploads` | 21:00 |

## 7. Quota YouTube API

Mặc định 10.000 unit/ngày, reset theo giờ Thái Bình Dương (~14–15h giờ VN). Ước tính hiện tại (≈200 kênh theo dõi):

| Tác vụ | Unit/ngày (ước tính) |
|---|---|
| `trending` + `stats` × 8 lần | ~250–350 |
| `channels` + `uploads` × 1 lần | ~250–300 |
| **Tổng** | **~500–650 / 10.000** |

## 8. Quy ước dữ liệu Raw

Đường dẫn object trên MinIO (và bản local trong `data/`):
```
raw/youtube/<job>/dt=<ngày UTC>/<crawler_id>_<giờ UTC>_p<số trang>.json
```
Mỗi file là một **envelope** bọc quanh response gốc, không sửa gì bên trong `response`:
```json
{
  "crawler_id": "ban",
  "job": "trending",
  "crawl_time_utc": "2026-09-24T01:00:03Z",
  "request": {"endpoint": "videos.list", "params": {"...": "..."}},
  "page_index": 0,
  "response": { "...nguyên văn API trả về..." }
}
```
`request.params` không chứa API key. Thư mục `state/` trên MinIO (`state/channels.json`, `state/tracked_videos.json`) là dữ liệu do code tính ra để điều khiển lần crawl sau, **không phải** raw.

## 9. Xem dữ liệu

- MinIO Console: `http://localhost:9001` → bucket `youtube-raw`
- Bản local (nếu bật `SAVE_LOCAL_COPY`): thư mục `data/raw/`
- pgAdmin: `http://localhost:5050` (dùng sau khi có tầng Processing)

## 10. Cấu trúc thư mục

```
├── .env.example          # Mẫu biến môi trường — commit; .env thật thì KHÔNG
├── docker-compose.yml     # MinIO + Postgres + pgAdmin
├── requirements.txt
├── AI_Log.md              # Nhật ký sử dụng AI
├── data/raw/               # Bản sao local của raw (không commit, xem .gitignore)
├── logs/                   # Log mỗi lần crawl
├── src/
│   ├── ingestion/
│   │   ├── crawler.py       # Điểm chạy: điều phối job, log, exit code
│   │   ├── youtube_client.py# Gọi YouTube API: retry, đếm quota
│   │   ├── raw.py           # Quy ước tên file & envelope tầng raw
│   │   ├── parts.py         # Danh sách part xin từ API
│   │   └── jobs/             # trending.py, channels.py, uploads.py, stats.py
│   └── utils/
│       ├── config.py         # Đọc & kiểm tra .env
│       ├── minio_client.py   # Kết nối MinIO, ghi/đọc JSON
│       └── sync_local.py     # Đồng bộ MinIO -> data/raw
├── notebooks/              # EDA (Report 3)
└── reports/                 # Báo cáo PDF nộp định kỳ
```

## 11. Xử lý sự cố thường gặp

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| `No module named 'src'` | Chạy bằng nút ▶ hoặc sai thư mục | Đứng ở gốc repo, chạy `python -m ...` |
| `No module named 'googleapiclient'` / `'minio'` | Chưa kích hoạt venv | `.\.venv\Scripts\Activate.ps1` |
| `Thiếu biến trong .env: ...` | `.env` thiếu hoặc để trống biến | Đối chiếu `.env.example` |
| `MaxRetryError` / `Connection refused` cổng 9000 | MinIO chưa chạy hoặc sai `MINIO_ENDPOINT` | `docker compose ps`; kiểm tra cổng 9000 (API) khác 9001 (Console) |
| `InvalidAccessKeyId` / `SignatureDoesNotMatch` | User/pass MinIO trong `.env` khác container | Sửa `.env` khớp với `docker-compose.yml` |
| `API key not valid` (400) | Sai API key | Lấy lại key từ Google Cloud Console |
| `accessNotConfigured` (403) | Project Google Cloud chưa bật API | Bật **YouTube Data API v3** |
| Exit code `2` | Hết quota trong ngày | Chờ quota reset (~14–15h giờ VN) |
| `docker compose up` báo `container name already in use` | Container cũ (project Docker Compose cũ) chưa xoá | `docker compose -p <tên-project-cũ> down -v` |

## 12. Trạng thái dự án

- ✅ Report 1: đã xác định giả thuyết, kiến trúc hệ thống
- ✅ Report 2 (đang làm): tầng Ingestion → MinIO đã chạy được 4 job; tầng Processing → Postgres chưa làm
- ⬜ Report 3, 4, 5: chưa bắt đầu
