@echo off
chcp 65001 > nul
echo === Bat dau chay job Channels & Uploads (Dinh ky) ===
python -m src.ingestion.crawler --job channels uploads