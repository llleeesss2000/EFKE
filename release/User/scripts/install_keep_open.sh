#!/usr/bin/env bash
cd "$(dirname "$0")/..
PAUSE_ON_EXIT=0 ./install.sh --no-pause
status=$?
echo
if [ "$status" -eq 0 ]; then
  echo "User 安裝完成。下一步請執行 ./start_keep_open.sh"
else
  echo "User 安裝失敗，請看上方錯誤訊息。"
fi
echo
read -r -p "按 Enter 關閉這個視窗..."
exit "$status"
