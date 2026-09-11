# BanNH_QE210137_GAMEANALYTICS_T1
# 
BanNH_QE210137_GAMEANALYTICS_T1/
│
├── .gitignore               # Loại bỏ file rác, file .env, __pycache__
├── README.md                # Hướng dẫn setup và chạy dự án (BẮT BUỘC)
├── AI_Log.md                # Nhật ký sử dụng AI (Prompt engineering log)
├── docker-compose.yml       # File khởi chạy toàn bộ hệ thống (MinIO, DB, App)
├── requirements.txt         # Các thư viện Python cần thiết
│
├── configs/                 # Chứa file cấu hình (nếu có)
│   └── db_config.json
│
├── docker/                  # Các file Dockerfile cho từng service
│   ├── app/
│   │   └── Dockerfile
│   └── db/                  # (Optional nếu dùng image gốc)
│
├── data/                    # Dữ liệu mẫu (Sample only - KHÔNG UP DỮ LIỆU LỚN LÊN GITHUB)
│   ├── raw/
│   └── processed/
│
├── src/                     # Source code chính
│   ├── ingestion/           # Code Crawl/API
│   │   └── crawler.py
│   ├── processing/          # Code làm sạch & ETL
│   │   └── cleaner.py
│   ├── modeling/            # Code Machine Learning
│   │   └── model.py
│   └── utils/               # Các hàm tiện ích dùng chung
│
├── notebooks/               # Jupyter Notebooks & RMarkdown (Dùng để phân tích/EDA)
│   ├── 1_Exploration.ipynb
│   └── 2_Modeling.ipynb
│
└── reports/                 # Các file báo cáo PDF nộp định kỳ
    ├── Report_1_Proposal.pdf
    └── Report_2_DataEngineering.pdf
