#!/usr/bin/env bash
cd "$(dirname "$0")/..
PAUSE_ON_EXIT=0 ./start.sh --no-pause
status=$?
echo
if [ "$status" -eq 0 ]; then
  echo "請打開：http://127.0.0.1:6161"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://127.0.0.1:6161" >/dev/null 2>&1 || true
  fi
else
  echo "User 啟動失敗，請看上方錯誤訊息。"
fi
echo
read -r -p "按 Enter 關閉這個視窗..."
exit "$status"
