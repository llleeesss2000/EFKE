@echo off
chcp 65001 >nul 2>&1
title Evidence-First Server

echo ============================================
echo   Evidence-First Server 安裝
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
python -m pip install -r requirements-server.txt
python -m pip install -U mineru
python -m pip install -U "torch>=2.6.0" torchvision
python -m pip install -U "transformers>=4.57.3,<5.0.0" safetensors tokenizers
python -m pip install -U ftfy hf_transfer

if not exist .env copy .env.example .env
mkdir server_data\originals server_data\derived server_data\backups logs 2>nul

echo.
echo 安裝完成！請執行 start.bat 啟動 Server。
pause
