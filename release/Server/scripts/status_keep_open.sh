#!/usr/bin/env bash
cd "$(dirname "$0")/..
echo "== Evidence-First Server 狀態 =="
if [ -f server.pid ] && kill -0 "$(cat server.pid)" 2>/dev/null; then
  echo "狀態：執行中"
  echo "PID：$(cat server.pid)"
else
  echo "狀態：未執行，或 pid 檔已失效"
fi
echo
if command -v ss >/dev/null 2>&1 && ss -ltn | grep -q ':8000 '; then
  echo "Port 8000：已開啟"
else
  echo "Port 8000：未偵測到 listen"
fi
echo
if [ -d .venv ]; then
  echo "venv：已建立"
else
  echo "venv：尚未建立，請先執行 install_keep_open.sh"
fi
echo
if [ -f server_data/metadata.db ]; then
  echo "資料庫：server_data/metadata.db 已存在"
else
  echo "資料庫：尚未建立"
fi
echo
echo "Server URL：http://127.0.0.1:8000"
echo "API 文件：http://127.0.0.1:8000/docs"
echo "最近 log："
tail -30 logs/server.log 2>/dev/null || echo "尚無 log"
echo
read -r -p "按 Enter 關閉這個視窗..."
