@echo off
chcp 65001 >nul 2>&1
title Evidence-First User

if not exist .venv\Scripts\activate.bat (
    echo 虛擬環境不存在，請先執行 install.bat
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

if not exist .env copy .env.example .env

for /f "tokens=1,* delims==" %%a in (.env) do (
    if "%%a"=="USER_WEB_PORT" set USER_WEB_PORT=%%b
    if "%%a"=="SERVER_API_URL" set SERVER_API_URL=%%b
)
if "%USER_WEB_PORT%"=="" set USER_WEB_PORT=6161
if "%SERVER_API_URL%"=="" set SERVER_API_URL=http://127.0.0.1:8000

echo ============================================
echo   Evidence-First User Web UI 啟動中...
echo ============================================
echo.
echo   瀏覽器網址：http://127.0.0.1:%USER_WEB_PORT%
echo   Server 位址：%SERVER_API_URL%
echo.
echo   按 Ctrl+C 停止 User
echo ============================================
echo.

start http://127.0.0.1:%USER_WEB_PORT%
uvicorn app.main:app --host 0.0.0.0 --port %USER_WEB_PORT%
pause
