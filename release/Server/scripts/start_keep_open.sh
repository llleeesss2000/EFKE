#!/usr/bin/env bash
cd "$(dirname "$0")/..
PAUSE_ON_EXIT=0 ./start.sh --no-pause
status=$?
echo
if [ "$status" -eq 0 ]; then
  echo "Server 已啟動。API 文件：http://127.0.0.1:8000/docs"
else
  echo "Server 啟動失敗，請看上方錯誤訊息。"
fi
echo
read -r -p "按 Enter 關閉這個視窗..."
exit "$status"
