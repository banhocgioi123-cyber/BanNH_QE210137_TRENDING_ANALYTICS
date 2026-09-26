# Thời điểm vàng trên YouTube Việt Nam

**Đồ án ADY201m — Advanced Data Engineering & Science Bootcamp, FPT University**
Chủ đề 4: Trending Content (YouTube) · Thành viên: BanNH – QE210137

> Upload video vào **giờ hành chính** hay **giờ nghỉ ngơi** thì dễ lọt Top Trending hơn?

Repo này chứa toàn bộ pipeline: thu thập dữ liệu từ YouTube Data API v3 → Data Lake (MinIO) → làm sạch (PostgreSQL) → phân tích và mô hình hoá. README gồm hai phần: **Phần A** giải thích bài toán và vì sao dữ liệu được thu thập theo cách này; **Phần B** hướng dẫn cài đặt và chạy. Chi tiết vận hành hằng ngày nằm ở [`docs/VAN_HANH.md`](docs/VAN_HANH.md).

---

# PHẦN A — BÀI TOÁN

## 1. Câu hỏi và giả thuyết

**Đơn vị phân tích:** một video, đăng bởi một kênh YouTube Việt Nam.

Câu hỏi được kiểm định bằng một giả thuyết duy nhất:

**H₀:** Xác suất lọt trending của video đăng trong giờ hành chính **bằng** video đăng trong giờ nghỉ, khi đã kiểm soát quy mô kênh, thể loại và thời lượng.
**H₁:** Hai xác suất này **khác nhau**.

Bác bỏ H₀ nếu hệ số của biến khung giờ trong hồi quy logistic có ý nghĩa thống kê (p < 0,05), tức khoảng tin cậy 95% của odds ratio không chứa 1.

## 2. Định nghĩa

| Khái niệm | Định nghĩa trong đồ án |
|---|---|
| **Giờ đăng** | `snippet.publishedAt`, đổi sang giờ Việt Nam (UTC+7). Với Premiere/livestream, dùng `liveStreamingDetails.actualStartTime` (giờ khán giả thực sự xem được) |
| **Giờ hành chính** | 08:00–17:00, thứ 2 đến thứ 6, giờ Việt Nam |
| **Giờ nghỉ** | Mọi thời điểm còn lại: buổi tối, ban đêm, cả ngày thứ 7 và chủ nhật |
| **Lọt trending** | Xuất hiện trong ít nhất một lần chụp danh sách `mostPopular` (khu vực VN) trong vòng **72 giờ** kể từ lúc đăng |
| **View sau 48h** | Số view tại mốc 48 giờ sau khi đăng, nội suy tuyến tính giữa hai lần chụp gần mốc nhất |
| **View chuẩn hoá** (dữ liệu lịch sử) | `log(1 + viewCount)`, với tuổi video là biến kiểm soát; chỉ dùng video từ 14 ngày tuổi trở lên, khi lượt xem đã tương đối ổn định |
| **Kênh Việt Nam** | Kênh có `country = VN`, hoặc không khai quốc gia nhưng ngôn ngữ mặc định là tiếng Việt |

Ngoài phân loại hai khung giờ, dữ liệu còn cho phép phân tích chi tiết hơn theo **24 giờ trong ngày** và **7 ngày trong tuần**.

## 3. Bảng dữ liệu đích

Mọi quyết định thu thập đều nhằm dựng được bảng sau. Mỗi dòng là một video:

| video_id | giờ đăng (VN) | khung giờ | lọt trending? | view sau 48h | subscriber kênh | thể loại | thời lượng |
|---|---|---|---|---|---|---|---|
| abc | 19:30 T6 | nghỉ | 1 | 850.000 | 2,1 triệu | Music | 4 phút |
| xyz | 10:00 T3 | hành chính | 0 | 120.000 | 2,1 triệu | Music | 3 phút |

Crawler chỉ thu thập nguyên liệu thô. Bảng này được dựng ở tầng Processing.

## 4. Vì sao không chỉ cần "gọi API lấy trending"

Nếu chỉ lấy danh sách trending, nghiên cứu sẽ rơi vào sáu cái bẫy. Mỗi bẫy dẫn đến một quyết định thiết kế:

| # | Bẫy | Hậu quả nếu bỏ qua | Cách giải quyết |
|---|---|---|---|
| 1 | Trending là **khoảnh khắc**, API không lưu lịch sử | Video trending vài giờ bị bỏ lỡ, gán nhầm là "không trending" | Chụp trending **mỗi giờ**, lưu nguyên văn |
| 2 | Chỉ có video trending thì **không có gì để so sánh** (survivorship bias) | "70% video trending đăng buổi tối" không chứng minh được gì | Thu thập **mọi video** của cùng các kênh làm nhóm so sánh |
| 3 | Nhóm so sánh phải **công bằng** | Tìm video ngẫu nhiên cho ra video khác ngôn ngữ, khác thời kỳ | Nhóm so sánh lấy từ **chính các kênh đó**, cùng giai đoạn đăng |
| 4 | **Biến gây nhiễu**: kênh lớn vừa dễ trending vừa có thói quen đăng giờ riêng | Kết luận nhầm "giờ X là giờ vàng" | Thu thập số subscriber, thể loại, thời lượng làm biến kiểm soát |
| 5 | Định nghĩa trending đã **bị YouTube thay đổi** (07/2025) | Nhãn trending lệch về Âm nhạc/Game | Không có biến thay thế trong đồ án này — ghi nhận là **hạn chế**: kết luận chủ yếu đúng cho các thể loại đang được đưa vào trending (mục 10) |
| 6 | **Thời gian phức tạp**: API trả giờ UTC; Premiere có giờ phát sóng riêng; video có thể trending muộn | Lệch 7 tiếng, nhãn sai | Lưu giờ gốc, xử lý múi giờ và gắn nhãn ở tầng Processing, sau khi có đủ lịch sử |

## 5. Dữ liệu được thu thập như thế nào

### Sáu job, mỗi job trả lời một mảnh của câu hỏi

```
trending ──► channels ──► discover ──► uploads ──► stats
                               └──────► backfill
```

| Job | Làm gì | Cung cấp cho nghiên cứu |
|---|---|---|
| `trending` | Chụp danh sách trending VN mỗi giờ (~200 video/lần) | **Biến kết quả** của Giả thuyết 1, kèm thứ hạng |
| `channels` | Tra thông tin các kênh từng có video trending | **Biến kiểm soát**: subscriber, tuổi kênh |
| `discover` | Mở rộng danh sách kênh Việt Nam qua tìm kiếm theo 76 từ khoá và mục "kênh nổi bật" | Tăng số kênh lên ~2.500, **đa dạng thể loại** ngoài Âm nhạc/Game |
| `uploads` | Lấy **mọi** video mới đăng của các kênh đang theo dõi, 2 lần/ngày | **Nhóm so sánh** (video không trending) và **biến giải thích** (giờ đăng) |
| `stats` | Chụp view/like/comment của video mới mỗi 3 giờ trong 3 ngày đầu | Không dùng để kiểm định giả thuyết (view là hệ quả của lọt trending); giữ cho tham khảo/EDA |
| `backfill` | Lấy lùi video 90 ngày của mọi kênh, tối đa 200 video/kênh | Không có nhãn trending, không dùng để kiểm định; giữ cho EDA và khối lượng Data Lake |

Nhãn trending/không trending **không** được gắn lúc thu thập, vì một video đăng hôm nay có thể lên trending vào ngày mai. Việc này làm ở tầng Processing khi đã đủ 72 giờ quan sát.

### Ba tầng dữ liệu

Giai đoạn thu thập chính: **25/9 – 9/10/2026**. Số lượng dưới đây là ước tính, sẽ cập nhật theo số liệu thật.

| Tầng | Nguồn | Số video (ước tính) | Nhãn trending | Dùng cho |
|---|---|---|---|---|
| **A. Lịch sử** | `backfill` | ~50.000–150.000 | Không có | Không dùng để kiểm định — tham khảo/EDA |
| **B. Thời gian thực** | `uploads` + `stats` | ~10.000–15.000 | Có | Mẫu chính để kiểm định giả thuyết — dữ liệu chất lượng cao nhất |
| **C. Trending** | `trending` | vài trăm – ~1.000 video lọt trending | Có | Nhóm dương tính (nhãn 1) |

**Chốt nhãn:** chỉ gắn nhãn trending cho video đăng **trước 6/10/2026**, để mọi video có đủ 72 giờ quan sát trước ngày kết thúc 9/10.

### Các biện pháp bảo đảm chất lượng khi huấn luyện mô hình

| Rủi ro | Biện pháp |
|---|---|
| Vài kênh đăng rất nhiều áp đảo dữ liệu | Tối đa 200 video/kênh ở tầng lịch sử |
| Nhãn trending nhiễu | Chụp mỗi giờ; chỉ gắn nhãn cho video theo dõi được từ lúc đăng |
| Video đăng sát ngày chốt chưa kịp trending | Loại video đăng sau 6/10 khỏi Giả thuyết 1 |
| Rất ít video lọt trending so với không lọt | Dùng class weight; đánh giá bằng PR-AUC thay vì accuracy |
| Rò rỉ dữ liệu giữa tập train và test | Chia train/test **theo kênh**: mọi video của một kênh nằm cùng một phía |

## 6. Phạm vi và hạn chế

- **Định nghĩa trending đã thay đổi.** Từ 21/07/2025, chart `mostPopular` của YouTube Data API chỉ lấy video từ các bảng xếp hạng Âm nhạc, Phim và Game. Kết luận của Giả thuyết 1 vì vậy chủ yếu đúng cho các thể loại này.
- **Nhóm kênh không đại diện cho toàn bộ YouTube Việt Nam.** Kênh đến từ trending và từ tìm kiếm theo từ khoá, nên thiên về kênh đang hoạt động. Kết luận đúng trong phạm vi *các kênh Việt Nam có hoạt động đăng tải thường xuyên*.
- **Không có dislike.** API không trả số dislike từ 2021; đề tài không dùng biến này.
- **Số subscriber là số hiện tại**, đã bị YouTube làm tròn, và với video lịch sử có thể khác lúc video được đăng.
- **Nhận diện kênh Việt Nam dựa trên khai báo của kênh**; kênh Việt không khai quốc gia lẫn ngôn ngữ sẽ bị bỏ sót.
- **Quota 10.000 unit/ngày** giới hạn tốc độ mở rộng; không dùng nhiều project để lách quota vì vi phạm chính sách của YouTube.

---

# PHẦN B — CHẠY DỰ ÁN

## 7. Kiến trúc

```
YouTube Data API v3
        │
        ▼
 [1] Ingestion (Python)    src/ingestion/  — 6 job, lưu JSON nguyên văn
        │
        ▼
   MinIO (Data Lake)       + bản sao ở data/raw/ trên máy
        │
        ▼
 [2] Processing            src/processing/ — làm sạch, đổi múi giờ, gắn nhãn   (chưa làm)
        │
        ▼
   PostgreSQL
        │
        ▼
 [3] Phân tích & mô hình   notebooks/, RStudio                                 (chưa làm)
```

| Container | Vai trò | Địa chỉ |
|---|---|---|
| `ady201m_minio` | Data Lake, lưu JSON thô | Console: `http://localhost:9001` |
| `ady201m_postgres` | Database sau khi làm sạch | `localhost:5432` |
| `ady201m_pgadmin` | Giao diện quản trị Postgres | `http://localhost:5050` |

## 8. Cài đặt

**Yêu cầu:** Docker Desktop, Python 3.11+, một YouTube Data API key (Google Cloud Console → bật **YouTube Data API v3**).

```powershell
git clone <repo-url>
cd BanNH_QE210137_TRENDING_ANALYTICS

# 1. Tạo .env từ mẫu rồi điền giá trị thật (KHÔNG commit .env)
copy .env.example .env

# 2. Bật hạ tầng
docker compose up -d
docker compose ps           # 3 container phải ở trạng thái running

# 3. Cài Python
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Các biến quan trọng trong `.env` (xem đầy đủ trong `.env.example`):

| Biến | Ý nghĩa |
|---|---|
| `YOUTUBE_API_KEY` | API key của bạn |
| `CRAWLER_ID` | Định danh máy crawl (chữ thường, số, `_`, `-`), gắn vào tên mọi file |
| `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` | Phải khớp với container MinIO |
| `QUOTA_DAILY_BUDGET`, `QUOTA_CORE_RESERVE` | Ngân sách quota theo ngày (mặc định 9.500 và 2.500) |

## 9. Chạy

Luôn chạy bằng `python -m` từ **thư mục gốc repo**.

```powershell
# Lần đầu: khởi tạo đủ dữ liệu cho mọi job
python -m src.ingestion.crawler --job trending channels uploads stats

# Chạy định kỳ (cài bằng Task Scheduler, xem docs/VAN_HANH.md)
python -m src.ingestion.crawler --job trending               # mỗi giờ
python -m src.ingestion.crawler --job stats                  # mỗi 3 giờ
python -m src.ingestion.crawler --job channels uploads       # 09:00 và 21:00
python -m src.ingestion.crawler --job discover backfill      # 14:30, ngay sau khi quota reset

# Tải dữ liệu từ MinIO về data/raw/ khi bản local bị thiếu
python -m src.utils.sync_local
```

Exit code: `0` thành công · `1` lỗi · `2` hết quota. Log ở `logs/crawl_<ngày>.log`.

Dữ liệu xem tại MinIO Console (`http://localhost:9001`, bucket `youtube-raw`) hoặc thư mục `data/raw/`.

## 10. Cấu trúc thư mục

```
├── README.md
├── docs/VAN_HANH.md          # Lịch chạy, quota, quy ước dữ liệu, xử lý sự cố
├── AI_Log.md                 # Nhật ký sử dụng AI
├── docker-compose.yml        # MinIO + PostgreSQL + pgAdmin
├── requirements.txt
├── .env.example              # Mẫu biến môi trường
├── configs/
│   └── discover_keywords.txt # Từ khoá tìm kênh cho job discover
├── src/
│   ├── ingestion/
│   │   ├── crawler.py        # Điểm chạy: điều phối job, ngân sách quota, log
│   │   ├── youtube_client.py # Gọi API: thử lại, đếm quota
│   │   ├── quota.py          # Ngân sách quota theo ngày
│   │   ├── raw.py            # Quy ước tên file và envelope tầng raw
│   │   ├── parts.py          # Các trường dữ liệu xin từ API
│   │   └── jobs/             # trending, channels, discover, uploads, backfill, stats
│   ├── processing/           # Làm sạch & ETL (Report 3)
│   ├── modeling/             # Mô hình (Report 4)
│   └── utils/                # config, minio_client, sync_local
├── data/raw/                 # Bản sao local của dữ liệu thô (không commit)
├── notebooks/                # EDA & mô hình
└── reports/                  # Báo cáo PDF
```

## 11. Tiến độ

| Report | Nội dung | Trạng thái |
|---|---|---|
| 1 | Giả thuyết, kiến trúc | Đang hoàn thiện |
| 2 | Pipeline Crawl → MinIO → DB | Tầng thu thập hoàn tất (6 job, chạy tự động); tầng MinIO → PostgreSQL chưa làm |
| 3 | Làm sạch, EDA, Data Dictionary | Chưa bắt đầu |
| 4 | Hai mô hình kiểm định giả thuyết | Chưa bắt đầu |
| 5 | Đóng gói Docker Compose, bảo vệ | Chưa bắt đầu |