@echo off
chcp 65001 > nul
echo === Bat dau chay job Trending (Moi gio) ===
python -m src.ingestion.crawler --job trending