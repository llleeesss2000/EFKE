#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
cd "$BASE_DIR"
PAUSE_ON_EXIT="${PAUSE_ON_EXIT:-1}"
if [ "${1:-}" = "--no-pause" ]; then
  PAUSE_ON_EXIT=0
fi

finish() {
  local code=$?
  if [ "$code" -ne 0 ]; then
    echo
    echo "User Web UI 啟動失敗，最近 log："
    tail -80 logs/user.log 2>/dev/null || true
  fi
  if [ "$PAUSE_ON_EXIT" = "1" ] && [ -t 0 ]; then
    echo
    read -r -p "按 Enter 關閉此視窗..."
  fi
  exit "$code"
}
trap finish EXIT

test -f .env || cp .env.example .env
set -a
. ./.env
set +a
USER_WEB_HOST="${USER_WEB_HOST:-0.0.0.0}"
USER_WEB_PORT="${USER_WEB_PORT:-6161}"
mkdir -p logs user_data

if [ -f user.pid ] && kill -0 "$(cat user.pid)" 2>/dev/null; then
  echo "User Web UI 已在執行：PID $(cat user.pid)"
  echo "User Web UI: http://127.0.0.1:${USER_WEB_PORT}"
  exit 0
fi
rm -f user.pid

if [ ! -x .venv/bin/python ] || [ ! -x .venv/bin/uvicorn ]; then
  echo "venv 不存在或不可用，先自動執行安裝。"
  PAUSE_ON_EXIT=0 "$(dirname "$0")/install.sh" --no-pause
fi

VENV_PY="$BASE_DIR/.venv/bin/python"
if ! grep -Fq "$VENV_PY" .venv/bin/uvicorn 2>/dev/null; then
  echo "偵測到 venv 指向舊路徑，重新建立 venv。"
  mv .venv ".venv.broken.$(date +%Y%m%d_%H%M%S)"
  PAUSE_ON_EXIT=0 "$(dirname "$0")/install.sh" --no-pause
fi

if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -q ":${USER_WEB_PORT} "; then
  listener_pid="$(ss -ltnp 2>/dev/null | grep ":${USER_WEB_PORT} " | sed -n 's/.*pid=\([0-9]*\).*/\1/p' | head -n 1)"
  if curl -sS --max-time 2 "http://127.0.0.1:${USER_WEB_PORT}/api/config" >/dev/null 2>&1; then
    [ -n "$listener_pid" ] && echo "$listener_pid" > user.pid
    echo "User Web UI 已在執行：PID ${listener_pid:-unknown}"
    echo "User Web UI: http://127.0.0.1:${USER_WEB_PORT}"
    exit 0
  fi
  echo "Port ${USER_WEB_PORT} 已被占用，但不是可辨識的 User Web UI。"
  echo "請先找出占用程序，或修改 .env 的 USER_WEB_PORT。"
  exit 1
fi

. .venv/bin/activate
setsid uvicorn app.main:app --host "$USER_WEB_HOST" --port "$USER_WEB_PORT" > logs/user.log 2>&1 < /dev/null &
echo $! > user.pid
sleep 1
kill -0 "$(cat user.pid)" 2>/dev/null

echo ""
echo "============================================"
echo "  Evidence-First User Web UI 已啟動"
echo "============================================"
echo ""
echo "  瀏覽器網址：http://127.0.0.1:${USER_WEB_PORT}"
echo "  Server 位址：${SERVER_API_URL:-http://127.0.0.1:8000}"
echo "  LLM 位址：${LLM_BASE_URL:-未設定}"
echo "  Log 路徑：$BASE_DIR/logs/user.log"
echo "============================================"

OPEN_URL="http://127.0.0.1:${USER_WEB_PORT}"
if command -v xdg-open >/dev/null 2>&1; then
  (sleep 1 && xdg-open "$OPEN_URL") &
elif command -v open >/dev/null 2>&1; then
  (sleep 1 && open "$OPEN_URL") &
elif command -v sensible-browser >/dev/null 2>&1; then
  (sleep 1 && sensible-browser "$OPEN_URL") &
fi
echo "正在自動開啟瀏覽器..."
