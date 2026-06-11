@echo off
chcp 65001 >nul 2>&1
title Evidence-First Server

if not exist .venv\Scripts\activate.bat (
    echo 虛擬環境不存在，請先執行 install.bat
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

if not exist .env copy .env.example .env

for /f "tokens=1,* delims==" %%a in (.env) do (
    if "%%a"=="SERVER_HOST" set SERVER_HOST=%%b
    if "%%a"=="SERVER_PORT" set SERVER_PORT=%%b
)
if "%SERVER_HOST%"=="" set SERVER_HOST=0.0.0.0
if "%SERVER_PORT%"=="" set SERVER_PORT=8000

echo ============================================
echo   Evidence-First Server 啟動中...
echo ============================================
echo.
echo   本機位址：http://127.0.0.1:%SERVER_PORT%
echo.

for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4" ^| findstr /v "127.0.0.1"') do (
    set LAN_IP=%%a
)
set LAN_IP=%LAN_IP: =%
if not "%LAN_IP%"=="" (
    echo   區域網路：http://%LAN_IP%:%SERVER_PORT%
    echo.
    echo   ★★★ 請將以下位址告訴使用 User 端的人：
    echo        http://%LAN_IP%:%SERVER_PORT%
)

echo.
echo   按 Ctrl+C 停止 Server
echo ============================================
echo.

uvicorn app.main:app --host %SERVER_HOST% --port %SERVER_PORT%
pause
