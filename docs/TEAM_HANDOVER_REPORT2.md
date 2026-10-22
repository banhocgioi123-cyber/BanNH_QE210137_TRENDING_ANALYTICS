# Bàn giao cho thành viên nhóm — Report 2 (Data Lake & Data Engineering)

Cập nhật: 22/10/2026 · Branch: `feat/add-youtube-crawler-script`

Tài liệu này tóm tắt những gì đã làm xong ở Report 2, cách hệ thống chạy, cách tự kiểm tra, và việc còn lại.
Chi tiết kỹ thuật từng thay đổi nằm ở `docs/REPORT2_WORKLOG.md`. Báo cáo nộp nằm ở `reports/Report_2_DataEngineering.md`.

---

## 1. Tóm tắt trong 30 giây

- Dữ liệu YouTube (khu vực VN) được crawl liên tục từ 24/09/2026 và lưu nguyên văn vào **MinIO** (Data Lake). Hiện có 165,393 file JSON, tổng 9.32 GB.
- Toàn bộ dữ liệu đã được **đọc từ MinIO, làm sạch và nạp vào PostgreSQL**: 9 bảng, 4 khoá ngoại, 5 view, khoảng 1.96 GB.
- Có sẵn **bảng phân tích có nhãn** `v_video_labels`: 137,264 video mới. Trong đó 964 video lên trending chính trong 72h đầu (0.70%), và 2,009 video lên trending theo danh mục (2.71% trên 74,208 video có nhãn này).
- **14 nhóm câu SQL kiểm tra** chạy không lỗi: không trùng khoá, không vi phạm khoá ngoại.
- Pipeline **chạy tự động bằng Windows Task Scheduler**: crawler ghi vào MinIO theo lịch, rồi cứ 3 giờ loader nạp phần mới vào DB.

---

## 2. Kiến trúc

```
YouTube Data API v3
      │  src/ingestion/crawler.py --job <tên job>       (Task Scheduler, mỗi 1–3 giờ)
      ▼
MinIO  bucket youtube-raw   raw/youtube/<job>/dt=<ngày UTC>/<crawler>_<HHMMSS>_pNN.json
      │  src/processing/cleaner.py --recent-days 2       (Task Scheduler "Nap DB", mỗi 3 giờ)
      ▼
PostgreSQL youtube_trending_db   9 bảng + 5 view
      │  configs/checks.sql, pgAdmin, RStudio/Jupyter (Report 3)
      ▼
Phân tích / mô hình
```

| Container | Vai trò | Truy cập |
|---|---|---|
| `ady201m_minio` | Data Lake | API `localhost:9000`, Console http://localhost:9001 |
| `ady201m_postgres` | Database | `localhost:5432` |
| `ady201m_pgadmin` | Giao diện xem DB | http://localhost:5050 |
| `ady201m_app` | Python (crawler + loader) trong Docker | `docker compose run --rm app` |

`minio`, `postgres` và `pgadmin` có `restart: unless-stopped`, nên tự bật lại khi Docker khởi động.

---

## 3. Những gì đã làm

### 3.1. Sửa cấu trúc repo theo đúng quy định của môn

Thiếu file hoặc thư mục bắt buộc thì report bị 0 điểm, nên phần này được làm đầu tiên.
- Tạo `docker/app/Dockerfile` và thêm service `app` vào `docker-compose.yml`.
- Chuyển `1_Exploration.ipynb` và `2_Modeling.ipynb` sang `notebooks/` (trước đây nằm nhầm trong `src/utils/`).
- Điền `configs/db_config.json`: host, port, tên DB. File này không chứa mật khẩu; mật khẩu chỉ nằm trong `.env`.
- Thêm thư viện `psycopg2-binary` vào `requirements.txt` và `pyproject.toml`.

### 3.2. Thiết kế database: `configs/schema.sql`

| Bảng | Nội dung |
|---|---|
| `raw_files` | Nhật ký mọi file đã nạp từ MinIO. Đây là minh chứng dữ liệu đi từ MinIO vào DB |
| `channels` | Thông tin kênh (bản mới nhất); `is_stub = true` là kênh tạm |
| `videos` | Metadata video: kênh, giờ đăng, danh mục, thời lượng, title, tags |
| `categories` | 32 danh mục video |
| `video_sources` | Video được thấy ở job nào. Dùng để tách dữ liệu backfill |
| `video_stats` | View/like/comment tại từng lần chụp |
| `trending_snapshots` | Mỗi lần video có mặt trên bảng xếp hạng (`main` hoặc `category`) |
| `playlist_items` | Danh sách video trong playlist của kênh |
| `discover_candidates` | Kênh ứng viên do job `discover` tìm được |

Khoá ngoại:
- `videos → channels`
- `videos → categories`
- `video_stats → videos`
- `trending_snapshots → videos`

`playlist_items` và `video_sources` **cố ý không có khoá ngoại** tới `videos`. Lý do: 136k video chỉ xuất hiện trong playlist (video cũ), crawler không lấy chi tiết nên chúng không có trong bảng `videos`.

### 3.3. Loader: `src/processing/cleaner.py`

Loader đọc từng file trên MinIO, làm sạch rồi ghi vào Postgres:
- Chuỗi thời gian → `TIMESTAMPTZ`.
- Thời lượng `PT1H2M3S` → số giây.
- Số đếm dạng chuỗi → số. Like hoặc comment bị ẩn → `NULL`.

Tính chất quan trọng:
- **Chạy lại bao nhiêu lần cũng không trùng dữ liệu.** File đã có trong `raw_files` sẽ bị bỏ qua, và mọi lệnh ghi dùng `ON CONFLICT`.
- **Mỗi lô 500 file ghi trong 1 transaction.** Chương trình chết giữa chừng cũng không để lại dữ liệu dở dang.
- **Đọc lỗi thì thử lại 3 lần.** Lỗi tạm thời của MinIO (`IncompleteBody`) đã từng xảy ra một lần.
- **Kênh tạm:** job `trending` chạy mỗi giờ, còn job `channels` chỉ 2 lần/ngày, nên video trending mới thường vào DB trước kênh của nó. Loader tạo kênh tạm để khoá ngoại không chặn video; lần nạp `channels` sau đó điền đủ thông tin. Nhờ vậy không mất video trending nào.
- **`--recent-days 2`:** chỉ xét các phân vùng ngày gần nhất, nên mỗi lần chạy mất khoảng 15 giây thay vì 3.5 phút. Nếu máy tắt nhiều ngày, loader tự nạp bù kể từ lần nạp cuối.

### 3.4. Tầng phân tích (view): `configs/labels.sql`

| View | Dùng để |
|---|---|
| `v_videos_analysis` | Video dùng cho phân tích, **đã bỏ backfill** và bỏ video của kênh tạm |
| `v_stats_analysis` | Số liệu tương tác tương ứng |
| `v_trending_rank` | Thứ hạng 1–200 trong từng lần chụp bảng xếp hạng |
| `v_cohort` | Video mới (job `uploads`), được theo dõi đủ 72 giờ |
| `v_video_labels` | **Bảng chính cho Report 3/4**: mỗi dòng là 1 video, kèm feature và 2 nhãn |

**Định nghĩa đã chốt:**
- **Giờ ra mắt `release_at`:** livestream/premiere dùng `actual_start_time`, vì YouTube đổi `publishedAt` của livestream thành lúc phát xong. Video thường dùng `published_at`.
- **`is_trending_main`:** video lên bảng trending chính trong 72 giờ kể từ `release_at`.
- **`is_trending_category`:** video lên bảng trending của một danh mục trong 72 giờ. Giá trị là `NULL` với video ra mắt trước 09/10, vì job này bắt đầu từ 09/10.
- Hai nhãn **tách riêng, không gộp**. Một video có thể có cả hai nhãn bằng 1.
- **Giờ hành chính:** 08:00–17:00, thứ 2 đến thứ 6, giờ VN.
- **Backfill** (lịch sử 30 ngày của kênh) vẫn nằm trong DB nhưng không dùng để phân tích, vì nhãn của nó không đáng tin.

### 3.5. SQL kiểm tra: `configs/checks.sql`

Output đầy đủ: `reports/report2_sql_checks_output.txt`. Kết quả chính:

| Kiểm tra | Kết quả |
|---|---|
| Trùng khoá chính | 0 |
| Vi phạm khoá ngoại | 0 |
| Lần chụp trước giờ đăng | 12,259 dòng livestream (do YouTube đổi `publishedAt`) và 1,438 dòng video thường lệch dưới 1h (do mốc chụp là lúc bắt đầu lượt crawl). Lệch thật sự ≥ 1h: 0 |
| View giảm giữa 2 lần chụp | 1.75%: YouTube lọc view ảo, ghi nhận và không sửa |
| Khoảng trống của crawler | 28 lần nghỉ trên 3 giờ, dài nhất 94 giờ: đây là **hạn chế**, cần ghi vào report |
| Có / không có backfill | 244,451 → 212,451 video; số video trending chính 1,508 → 1,505 |

### 3.6. Lịch chạy tự động (Windows Task Scheduler, thư mục `\ADY201m\`)

| Task | Lệnh | Lịch |
|---|---|---|
| Trending | `crawler --job trending` | mỗi giờ, phút :00 |
| Trending danh muc | `crawler --job trending_category` | mỗi 3 giờ, phút :40 |
| Stats | `crawler --job stats` | mỗi 3 giờ, phút :10 |
| Uploads | `crawler --job channels uploads` | 09:00 và 21:00 |
| Mo rong du lieu | `crawler --job discover backfill` | 14:30 (ngay sau khi quota reset) |
| **Nap DB** (mới) | `cleaner --source minio --recent-days 2` | mỗi 3 giờ, phút :50 |

- Mọi task chạy ẩn qua `conhost.exe --headless`. Trước đây cửa sổ console bị đóng nhầm từng làm chết job `Uploads`.
- Mọi task tự đánh thức máy khi sleep và chạy bù khi lỡ giờ.
- ⚠️ **Task chỉ chạy khi đang đăng nhập Windows.** Khoá màn hình thì vẫn chạy, nhưng **sign out thì dừng**. Lần chạy lúc 02:50 ngày 22/10 bị lỡ vì đã sign out.
- ⚠️ **Docker Desktop phải đang chạy.** Nên bật *Settings → General → Start Docker Desktop when you sign in*.
- Log nằm ở `logs/crawl_<ngày>.log` (crawler) và `logs/load_db.log` (loader).

---

## 4. Tự chạy và kiểm tra

Chạy các lệnh từ thư mục gốc repo, sau khi đã kích hoạt `.venv`.

Bật hạ tầng:

```bash
docker compose up -d minio postgres pgadmin
```

Nạp phần dữ liệu mới vào DB (chạy lại an toàn):

```bash
python -m src.processing.cleaner --recent-days 2
```

Quét lại toàn bộ MinIO (khoảng 3 phút liệt kê, dùng khi gộp dữ liệu từ máy khác):

```bash
python -m src.processing.cleaner
```

Chạy toàn bộ SQL kiểm tra:

```bash
docker exec -i ady201m_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < configs/checks.sql
```

Thống kê nhanh bản local `data/raw`:

```bash
python -m src.utils.data_stats
```

**Xem DB bằng pgAdmin** (http://localhost:5050, đăng nhập bằng `PGADMIN_DEFAULT_EMAIL`/`PASSWORD` trong `.env`):
1. Chuột phải **Servers**, chọn **Register → Server**. Host: `postgres` (không dùng `localhost`). Port: `5432`. Database, user, password lấy từ `.env`.
2. Mở **Databases → youtube_trending_db → Schemas → public**, rồi mở **Tables** hoặc **Views**.
3. Muốn xem dữ liệu: chuột phải vào bảng, chọn **View/Edit Data → First 100 Rows**. Không chọn *All Rows* với `playlist_items` (5.4M dòng).
4. Muốn xem toàn bộ lược đồ: chuột phải vào database, chọn **ERD For Database**.

Truy vấn nên thử đầu tiên:

```sql
SELECT * FROM v_video_labels WHERE is_trending_main LIMIT 50;
```

**Máy thành viên khác:** dữ liệu thật chỉ nằm trên MinIO của máy crawl. Muốn có dữ liệu thì dùng `mc mirror` để sao chép bucket `youtube-raw`, sau đó chạy loader. Nếu chỉ cần xem cấu trúc thì xem `data/raw/sample/` (11 file raw mẫu) và `data/processed/` (CSV mẫu khoảng 500 dòng).

---

## 5. Hạn chế cần biết khi phân tích

1. **Mất cân bằng mạnh:** positive dưới 3%. Report 4 dùng trọng số lớp và đánh giá bằng PR-AUC/F1/recall, không dùng accuracy.
2. **Crawler từng nghỉ** (dài nhất 94 giờ): video chỉ trending trong lúc crawler tắt sẽ bị gán nhầm nhãn 0.
3. **Bảng trending chính thiên về Game/Âm nhạc/Phim:** đây là thay đổi của YouTube từ 21/07/2025. Positive tập trung ở vài danh mục.
4. **Số liệu kênh là bản mới nhất,** không phải tại thời điểm video đăng.
5. **26 kênh tạm** chưa từng được `channels.list` trả về (có thể đã bị xoá hoặc khoá). Video của các kênh này nằm ngoài cohort, không ảnh hưởng nhãn.

---

## 6. Việc còn lại

| Việc | Ai | Ghi chú |
|---|---|---|
| Chèn 5 ảnh chụp màn hình vào report (`docker compose ps`, MinIO Console ×2, pgAdmin ×2) | Nhóm | Vị trí đánh dấu `[Ảnh N — chèn ảnh]` |
| Sửa dòng "Sinh viên" và xuất `reports/Report_2_DataEngineering.pdf` | Nhóm | |
| Commit theo nhóm file gợi ý trong `docs/REPORT2_WORKLOG.md` (mục 7, 9.5, 10) | Nhóm | Ít nhất 2 commit/tuần, message theo conventional commits |
| Ghi `AI_Log.md` | Nhóm | Bắt buộc theo quy định của môn |
| Bật lại 5 task crawler trong Task Scheduler | Chủ máy crawl | Hiện đang tạm tắt |
| Report 3: notebook làm sạch, EDA bằng RStudio, data dictionary | Tuần 21–27/10 | Dùng `v_video_labels` làm bảng chính |
