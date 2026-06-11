@echo off
chcp 65001 >nul 2>&1
title Evidence-First Server

:menu
cls
echo.
echo ╔══════════════════════════════════════════╗
echo ║     Evidence-First Server 控制面板       ║
echo ╠══════════════════════════════════════════╣
echo ║                                          ║

if exist server.pid (
    set /p PID=<server.pid
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
echo   2  啟動 Server
echo   3  停止 Server
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
echo 正在安裝 Server 環境...
call scripts\install.bat
goto menu

:start
echo.
if not exist .venv\Scripts\activate.bat (
    echo 虛擬環境不存在，請先執行「首次安裝」
    pause
    goto menu
)
if exist server.pid (
    set /p PID=<server.pid
    tasklist /fi "PID eq %PID%" 2>nul | findstr /i "python" >nul 2>&1
    if %errorlevel% equ 0 (
        echo Server 已在執行中
        pause
        goto menu
    )
)
call scripts\start.bat
goto menu

:stop
echo.
taskkill /f /im uvicorn.exe >nul 2>&1
del server.pid >nul 2>&1
echo Server 已停止
pause
goto menu

:status
echo.
if exist server.pid (
    set /p PID=<server.pid
    tasklist /fi "PID eq %PID%" 2>nul | findstr /i "python" >nul 2>&1
    if %errorlevel% equ 0 (
        echo Server 執行中 (PID %PID%)
    ) else (
        echo Server 未啟動
    )
) else (
    echo Server 未啟動
)
pause
goto menu

:exit
exit
