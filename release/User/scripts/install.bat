@echo off
chcp 65001 >nul 2>&1
title Evidence-First User

echo ============================================
echo   Evidence-First User 安裝
echo ============================================
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo 找不到 Python，請先安裝 Python 3.10 以上
    echo 下載位址：https://www.python.org/downloads/
    pause
    exit /b 1
)

python --version
echo.

if not exist .venv (
    echo 建立虛擬環境...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo 安裝依賴...
python -m pip install --upgrade pip
python -m pip install -r requirements-user.txt

if not exist .env copy .env.example .env
mkdir user_data logs 2>nul

echo.
echo 安裝完成！請執行 start.bat 啟動 User。
pause
