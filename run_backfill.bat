@echo off
chcp 65001 > nul
echo === Bat dau chay job Discover & Backfill (Nang quota) ===
python -m src.ingestion.crawler --job discover backfill