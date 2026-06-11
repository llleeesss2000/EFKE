#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/..
if test -f server.pid && kill -0 "$(cat server.pid)" 2>/dev/null; then
  kill "$(cat server.pid)"
  rm -f server.pid
  echo "Server 已停止"
else
  echo "Server 未執行"
fi

read -p "按 Enter 關閉此視窗..."
