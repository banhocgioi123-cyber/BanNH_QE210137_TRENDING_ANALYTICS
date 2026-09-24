# Vận hành pipeline thu thập

Tài liệu dành cho người chạy và bảo trì crawler. Bối cảnh bài toán xem ở [README](../README.md).

## 1. Lịch chạy tự động (Windows Task Scheduler)

Tạo 4 tác vụ. Mỗi tác vụ đặt **Start in** là thư mục gốc repo, **Program** là `python.exe` trong môi trường ảo (ví dụ `...\.venv\Scripts\python.exe`).

| Tác vụ | Arguments | Lịch | Ghi chú |
|---|---|---|---|
| Trending | `-m src.ingestion.crawler --job trending` | Mỗi giờ, phút :00 | ~4 unit/lần |
| Stats | `-m src.ingestion.crawler --job stats` | Mỗi 3 giờ, phút :10 | Lệch 10 phút với trending để ít chạy chồng |
| Uploads | `-m src.ingestion.crawler --job channels uploads` | 09:00 và 21:00 | Phát hiện video mới sớm để có mốc 48h |
| Mở rộng dữ liệu | `-m src.ingestion.crawler --job discover backfill` | 14:30 | Ngay sau khi quota reset |

Tác vụ "Mở rộng dữ liệu" tự đi đúng trình tự nhờ ngân sách quota: những ngày đầu `discover` dùng phần lớn quota dành cho job nặng; khi đủ 2.500 kênh hoặc hết từ khoá, `backfill` nhận phần quota còn lại. Không cần đổi lệnh theo ngày.

## 2. Quota YouTube API

Google cấp **10.000 unit/ngày/project**, reset lúc nửa đêm giờ Thái Bình Dương: **14:00 giờ Việt Nam** (15:00 từ tháng 11 đến tháng 3).

### Ngân sách tự động

Mọi lần chạy cộng dồn số unit đã dùng vào `state/quota/<ngày>.json` trên MinIO (ngày tính theo giờ Thái Bình Dương).

| Loại job | Job | Được dùng tới (tổng cả ngày) |
|---|---|---|
| Thiết yếu | `trending`, `stats`, `channels`, `uploads` | `QUOTA_DAILY_BUDGET` = **9.500** |
| Nặng | `discover`, `backfill` | 9.500 − `QUOTA_CORE_RESERVE` (2.500) = **7.000** |

- Job nặng chạm trần: crawler ghi cảnh báo `dừng vì đủ ngân sách hôm nay`, bỏ qua job đó, chạy tiếp các job sau. Tiến độ đã lưu, lần sau làm tiếp. Exit code vẫn là `0`.
- Job thiết yếu chạm trần: dừng với exit code `2`.
- Bộ đếm chỉ tính các lần gọi qua code này. Mức dùng thật: Google Cloud Console → APIs & Services → YouTube Data API v3 → **Quotas**.

### Chi phí từng job

| Job | Cách tính | Ví dụ thực tế |
|---|---|---|
| `trending` | ~4 unit/lần | 4 trang × 1 unit |
| `channels` | 1 unit / 50 kênh | 200 kênh → 4 unit |
| `uploads` | ~1 unit/kênh + 1 unit / 50 video mới | 200 kênh → 235 unit |
| `stats` | 1 unit / 50 video đang theo dõi | 1.693 video → 34 unit |
| `discover` | Search: **100 unit/lần** (tối đa 60 lần/lượt chạy); mục nổi bật: 1 unit/kênh | Gần như toàn bộ chi phí nằm ở search |
| `backfill` | ~5–8 unit/kênh | Kênh đăng nhiều tốn tới ~10 unit (giới hạn 200 video) |

**Không** dùng nhiều tài khoản/project Google để tăng quota cho cùng mục đích: chính sách YouTube cấm việc này và có thể thu hồi key hoặc khoá tài khoản. Thành viên nhóm dùng key riêng để **chạy thử** code là hợp lệ.

## 3. Quy ước dữ liệu

### Tầng raw

Đường dẫn object trên MinIO (bản local nằm ở `data/` với cùng cấu trúc):

```
raw/youtube/<job>/dt=<ngày UTC>/<crawler_id>_<giờ UTC>_p<số trang>.json
```

Các thư mục job: `trending/`, `channels/`, `uploads/playlist_items/`, `uploads/videos/`, `stats/`, `discover/search/`, `discover/sections/`, `discover/channels/`, `backfill/playlist_items/`, `backfill/videos/`.

Mỗi file là một **envelope** bọc response nguyên văn của API:

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

Nguyên tắc: **không sửa, không lọc, không bỏ bớt** những gì API trả về. `request.params` không chứa API key. Mọi xử lý (đổi múi giờ, gắn nhãn, loại trùng) làm ở tầng Processing.

### Tầng state

`state/` chứa dữ liệu do code tự tính ra để điều khiển lần chạy sau, **không phải** dữ liệu nghiên cứu:

| File | Nội dung | Ghi bởi → đọc bởi |
|---|---|---|
| `state/channels.json` | Kênh đang theo dõi, playlist uploads, lần cuối thấy trong trending, thời điểm được discover | `channels`, `discover` → `uploads`, `backfill`, `discover` |
| `state/tracked_videos.json` | Video mới đang theo dõi view (≤ 3 ngày tuổi) | `uploads` → `stats` |
| `state/discover.json` | Từ khoá đã tìm, kênh đã đọc mục nổi bật, kênh đã loại, ứng viên chưa xử lý | `discover` |
| `state/backfill.json` | Kênh đã backfill xong | `backfill` |
| `state/quota/<ngày>.json` | Tổng unit đã dùng trong ngày | `crawler` |

Xoá `state/` thì code vẫn chạy lại được (tốn thêm quota để dựng lại). Xoá `raw/` thì dữ liệu **mất vĩnh viễn**, vì các snapshot trending không thể thu thập lại.

### Bản sao local và gộp dữ liệu nhiều máy

- `SAVE_LOCAL_COPY=true`: mỗi file raw được ghi thêm vào `data/raw/`. MinIO vẫn là bản chính; lỗi ghi đĩa chỉ tạo cảnh báo.
- `python -m src.utils.sync_local`: tải về `data/raw/` những file có trên MinIO nhưng chưa có bản local. Chạy lại bao nhiêu lần cũng an toàn.
- Gộp dữ liệu từ máy khác: dùng MinIO Client `mc mirror` sao chép `raw/` giữa hai MinIO. Tên file chứa `CRAWLER_ID` nên không bị đè.

## 4. Theo dõi hằng ngày

| Dòng log | Ý nghĩa |
|---|---|
| `Quota ngày ...: đã dùng X/9500 unit` | Quota đã dùng trong ngày tính đến lúc bắt đầu chạy |
| `Discover: ... thêm N kênh Việt Nam, state có X/2500 kênh` | Tiến độ mở rộng kênh |
| `Backfill: ... M video từ K kênh (còn R kênh)` | Tiến độ lấy lịch sử; R = 0 là xong |
| `Uploads: ... thêm N video vào danh sách theo dõi` | Số video mới mỗi lần quét |
| `Job '...' dừng vì đủ ngân sách hôm nay` | Bình thường, lần sau làm tiếp |

## 5. Xử lý sự cố

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| `No module named 'src'` | Chạy bằng nút ▶ của VS Code hoặc sai thư mục | Đứng ở gốc repo, chạy `python -m ...` |
| `No module named 'googleapiclient'` / `'minio'` | Chưa kích hoạt môi trường ảo | `.\.venv\Scripts\Activate.ps1` |
| `Thiếu biến trong .env: ...` | Thiếu biến hoặc để trống | Đối chiếu `.env.example` |
| Cảnh báo `thiếu gói tzdata` | Windows không có dữ liệu múi giờ | `pip install tzdata` |
| `MaxRetryError` / `Connection refused` cổng 9000 | MinIO chưa chạy hoặc sai `MINIO_ENDPOINT` | `docker compose ps`; cổng 9000 là API, 9001 là Console |
| `InvalidAccessKeyId` / `SignatureDoesNotMatch` | User/password MinIO trong `.env` khác container | Sửa `.env` cho khớp |
| MinIO liên tục khởi động lại | `MINIO_ROOT_PASSWORD` ngắn hơn 8 ký tự | Đổi mật khẩu dài hơn |
| `API key not valid` (400) | Sai API key | Lấy lại key từ Google Cloud Console |
| `accessNotConfigured` (403) | Project chưa bật API | Bật **YouTube Data API v3** |
| Exit code `2` | Hết quota hoặc job thiết yếu chạm ngân sách | Chờ quota reset lúc 14:00 giờ VN |
| `container name already in use` | Container của project Docker Compose cũ còn sót | `docker compose -p <tên-project-cũ> down -v` |