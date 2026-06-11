@echo off
chcp 65001 >nul 2>&1
title Evidence-First User

:menu
cls
echo.
echo ╔══════════════════════════════════════════╗
echo ║     Evidence-First User 控制面板         ║
echo ╠══════════════════════════════════════════╣
echo ║                                          ║

if exist user.pid (
    set /p PID=<user.pid
    tasklist /fi "PID eq %PID%" 2>nul | findstr /i "python" >nul 2>&1
    if %errorlevel% equ 0 (
        echo   狀態：執行中 (PID %PID%)
    ) else (
        echo   狀態：未啟動
    )
) else (
    echo   狀態：未啟動
)

echo ║                                          ║
echo   1  首次安裝（建立 venv、安裝依賴）
echo   2  啟動 User（同步開啟瀏覽器）
echo   3  停止 User
echo   4  查看狀態
echo   0  離開
echo ║                                          ║
echo ╚══════════════════════════════════════════╝
echo.

set /p choice=請選擇 [0-4]: 

if "%choice%"=="1" goto install
if "%choice%"=="2" goto start
if "%choice%"=="3" goto stop
if "%choice%"=="4" goto status
if "%choice%"=="0" goto exit
goto menu

:install
echo.
echo 正在安裝 User 環境...
call scripts\install.bat
goto menu

:start
echo.
if not exist .venv\Scripts\activate.bat (
    echo 虛擬環境不存在，請先執行「首次安裝」
    pause
    goto menu
)
if exist user.pid (
    set /p PID=<user.pid
    tasklist /fi "PID eq %PID%" 2>nul | findstr /i "python" >nul 2>&1
    if %errorlevel% equ 0 (
        echo User Web UI 已在執行中
        pause
        goto menu
    )
)
call scripts\start.bat
goto menu

:stop
echo.
taskkill /f /im uvicorn.exe >nul 2>&1
del user.pid >nul 2>&1
echo User Web UI 已停止
pause
goto menu

:status
echo.
if exist user.pid (
    set /p PID=<user.pid
    tasklist /fi "PID eq %PID%" 2>nul | findstr /i "python" >nul 2>&1
    if %errorlevel% equ 0 (
        echo User 執行中 (PID %PID%)
    ) else (
        echo User 未啟動
    )
) else (
    echo User 未啟動
)
pause
goto menu

:exit
exit
