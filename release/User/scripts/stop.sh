#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/..
if test -f user.pid && kill -0 "$(cat user.pid)" 2>/dev/null; then
  kill "$(cat user.pid)"
  rm -f user.pid
  echo "User Web UI 已停止"
else
  echo "User Web UI 未執行"
fi

read -p "按 Enter 關閉此視窗..."
