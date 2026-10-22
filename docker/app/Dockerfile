# Container App: chạy crawler (ingestion) và loader (processing) trong cùng môi trường Python
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    TZ=Asia/Ho_Chi_Minh

WORKDIR /app

# Cài thư viện trước để Docker cache lớp này khi chỉ sửa code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY configs/ configs/

# Mặc định: nạp raw từ MinIO vào PostgreSQL (chạy lại an toàn, file đã nạp sẽ bỏ qua)
# Crawl: docker compose run --rm app python -m src.ingestion.crawler --job trending
CMD ["python", "-m", "src.processing.cleaner", "--source", "minio"]
