@echo off
chcp 65001 >nul
cd /d %~dp0
title Trending Analytics (uv)

echo ============================================
echo   Trending Analytics (uv)
echo   Thu muc: %cd%
echo ============================================
echo.
echo [1/2] Dong bo thu vien bang uv (uv sync)...
uv sync
if errorlevel 1 (
    echo.
    echo [LOI] uv sync that bai. Kiem tra pyproject.toml / ket noi mang.
    pause
    exit /b 1
)
echo.
echo [2/2] Kich hoat moi truong .venv
call .venv\Scripts\activate.bat
echo.
python --version
echo Python: %VIRTUAL_ENV%
echo.
echo Lenh hay dung:
echo   uv add ^<goi^>      them thu vien
echo   uv remove ^<goi^>   go thu vien
echo   uv run ^<lenh^>     chay lenh trong moi truong
echo   exit              thoat
echo.
cmd /k
