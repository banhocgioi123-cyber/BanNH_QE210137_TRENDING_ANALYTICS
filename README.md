 #  YouTube Trending Data Analytics (ADY201m)

Đồ án môn học ADY201m - Hệ thống tự động hóa thu thập và phân tích dữ liệu video thịnh hành (Trending) trên YouTube bằng Python.

##  Giới thiệu dự án
Dự án được xây dựng nhằm đơn giản hóa quy trình thu thập và xử lý dữ liệu (Data Pipeline). Thay vì sử dụng các hệ thống cồng kềnh, nhóm đã thiết kế một pipeline tinh gọn và hiệu quả:
1. **Thu thập trực tiếp:** Gọi **YouTube Data API v3** để lấy danh sách video thịnh hành theo khu vực
2. **Bóc tách dữ liệu:** Lọc các trường thông số quan trọng (Tiêu đề, Kênh, Lượt xem, Lượt thích, Bình luận...).
3. **Lưu trữ tối ưu:** Xuất trực tiếp dữ liệu dạng bảng phẳng thành file **`.csv`** sạch sẽ, sẵn sàng phục vụ cho việc phân tích, vẽ biểu đồ và làm báo cáo đồ án.

##  Cấu trúc thư mục dự án
BanNH_QE210137_TRENDING_ANALYTICS/
│
├── configs/            # Thư mục chứa cấu hình
│   └── db_config.json  # File cấu hình database
├── src/                # Mã nguồn chính của đồ án
│   ├── ingestion/      # Thu thập dữ liệu
│   │   ├── __init__.py
│   │   └── crawler.py  # Script cào dữ liệu từ YouTube API
│   ├── modeling/       # Xử lý và làm sạch dữ liệu
│   │   └── cleaner.py
│   ├── processing/     # Phân tích và mô hình hóa
│   │   └── model.py
│   └── utils/          # Các tiện ích và notebook phân tích
│       ├── 1_Exploration.ipynb
│       ├── 2_Modeling.ipynb
│       ├── __init__.py
│       └── config.py
├── .gitignore          # Bỏ qua các file không cần thiết trên git
├── AI_Log.md           # Nhật ký sử dụng AI / Prompt engineering log
├── README.md           # Tài liệu hướng dẫn đồ án
├── docker-compose.yml  # Cấu hình docker đa container
└── requirements.txt    # Danh sách thư viện Python
