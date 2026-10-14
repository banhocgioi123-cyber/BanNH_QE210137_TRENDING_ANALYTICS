#!/usr/bin/env python3
"""Nạp bộ export (exports/<region>/*.csv.gz) vào PostgreSQL.

Cách dùng:
    pip install psycopg2-binary python-dotenv
    python load_exports.py                       # nạp exports/us vào DB trống
    python load_exports.py --truncate            # xóa dữ liệu cũ rồi nạp lại
    python load_exports.py --data-dir exports/us --schema schema.sql

Thông tin kết nối đọc từ biến môi trường (hoặc file .env):
    POSTGRES_HOST (mặc định localhost), POSTGRES_PORT (mặc định 5432),
    POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD

Toàn bộ quá trình chạy trong 1 transaction: lỗi ở bất kỳ bảng nào thì
không có gì bị ghi vào database.
"""
import argparse
import csv
import gzip
import json
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2 import sql

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv là tùy chọn
    pass

# Thứ tự nạp: bảng cha trước, bảng con sau (do có khóa ngoại)
LOAD_ORDER = [
    "channels",
    "videos",
    "video_snapshots",
    "trending_snapshots",
    "playlist_items",
    "discover_hits",
    "channel_sections",
]


def connect():
    conn = psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "postgres"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )
    conn.set_client_encoding("UTF8")
    return conn


def copy_table(cur, table, path):
    """Stream 1 file .csv.gz vào bảng bằng COPY (nhanh hơn INSERT rất nhiều)."""
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        header = next(csv.reader([f.readline()]))
        columns = sql.SQL(", ").join(sql.Identifier(c) for c in header)
        stmt = sql.SQL(
            "COPY {} ({}) FROM STDIN WITH (FORMAT csv, HEADER false)"
        ).format(sql.Identifier(table), columns)
        cur.copy_expert(stmt.as_string(cur), f)


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--data-dir", default="exports/us", type=Path)
    parser.add_argument("--schema", default=here / "schema.sql", type=Path)
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="xóa sạch dữ liệu trong 7 bảng trước khi nạp",
    )
    args = parser.parse_args()

    # Kiểm tra đủ file trước khi đụng vào database
    missing = [t for t in LOAD_ORDER if not (args.data_dir / f"{t}.csv.gz").exists()]
    if missing:
        sys.exit(f"Thiếu file trong {args.data_dir}: {', '.join(m + '.csv.gz' for m in missing)}")

    manifest_path = args.data_dir / "manifest.json"
    expected = json.loads(manifest_path.read_text("utf-8"))["rows"] if manifest_path.exists() else {}

    conn = connect()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(args.schema.read_text("utf-8"))

            non_empty = []
            for t in LOAD_ORDER:
                cur.execute(sql.SQL("SELECT EXISTS (SELECT 1 FROM {})").format(sql.Identifier(t)))
                if cur.fetchone()[0]:
                    non_empty.append(t)

            if non_empty and not args.truncate:
                sys.exit(
                    "Các bảng đã có dữ liệu: " + ", ".join(non_empty)
                    + "\nChạy lại với --truncate nếu muốn xóa và nạp lại."
                )
            if args.truncate:
                names = sql.SQL(", ").join(sql.Identifier(t) for t in LOAD_ORDER)
                cur.execute(sql.SQL("TRUNCATE {} CASCADE").format(names))

            for t in LOAD_ORDER:
                print(f"Đang nạp {t} ...", end=" ", flush=True)
                copy_table(cur, t, args.data_dir / f"{t}.csv.gz")
                cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(t)))
                n = cur.fetchone()[0]
                note = ""
                if t in expected:
                    ok = "khớp manifest" if n == expected[t] else f"LỆCH, manifest ghi {expected[t]}"
                    note = f"({ok})"
                    if n != expected[t]:
                        raise RuntimeError(f"Số dòng bảng {t} không khớp manifest: {n} != {expected[t]}")
                print(f"{n:,} dòng {note}")
        print("Xong. Đã commit toàn bộ.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
