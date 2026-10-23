@echo off
chcp 65001 > nul
echo === Bat dau chay job Stats (Moi 3 gio) ===
python -m src.ingestion.crawler --job stats