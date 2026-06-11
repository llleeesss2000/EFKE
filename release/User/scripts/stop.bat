@echo off
chcp 65001 >nul 2>&1
taskkill /f /im uvicorn.exe >nul 2>&1
echo User Web UI 已停止
pause
