import os
import pandas as pd
from sqlalchemy import create_engine

DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "postgres")
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = os.getenv("POSTGRES_DB", "postgres")

ENGINE = create_engine(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

JOB_TABLE_MAP = {
    "data/processed/cleaned_trending.csv": "fact_trending",
    "data/processed/cleaned_channels.csv": "dim_channels",
    "data/processed/cleaned_videos.csv": "dim_videos",
    "data/processed/cleaned_stats.csv": "fact_stats",
    "data/processed/cleaned_playlist_items.csv": "dim_playlist_items",
    "data/processed/cleaned_discover.csv": "fact_discover",
}

def load_all_data():
    for csv_path, table_name in JOB_TABLE_MAP.items():
        if os.path.exists(csv_path):
            print(f" Đang đọc {csv_path}...")
            df = pd.read_csv(csv_path)
            df.to_sql(table_name, con=ENGINE, if_exists="append", index=False)
            print(f" Đã nạp {len(df)} dòng vào bảng {table_name}")
        else:
            print(f" Chưa có file làm sạch: {csv_path} (Bỏ qua)")

if __name__ == "__main__":
    load_all_data()