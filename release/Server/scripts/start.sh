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
    echo "Server 啟動失敗，最近 log："
    tail -80 logs/server.log 2>/dev/null || true
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
SERVER_HOST="${SERVER_HOST:-0.0.0.0}"
SERVER_PORT="${SERVER_PORT:-8000}"
mkdir -p logs server_data/originals server_data/derived server_data/backups

if [ -f server.pid ] && kill -0 "$(cat server.pid)" 2>/dev/null; then
  echo "Server 已在執行：PID $(cat server.pid)"
  echo "Server URL: http://127.0.0.1:${SERVER_PORT}"
  echo "LAN URL: http://$(hostname -I 2>/dev/null | awk '{print $1}'):${SERVER_PORT}"
  exit 0
fi
rm -f server.pid

if [ ! -x .venv/bin/python ] || [ ! -x .venv/bin/uvicorn ]; then
  echo "venv 不存在或不可用，先自動執行安裝。"
  PAUSE_ON_EXIT=0 ./install.sh --no-pause
fi

VENV_PY="$BASE_DIR/.venv/bin/python"
if ! grep -Fq "$VENV_PY" .venv/bin/uvicorn 2>/dev/null; then
  echo "偵測到 venv 指向舊路徑，重新建立 venv。"
  mv .venv ".venv.broken.$(date +%Y%m%d_%H%M%S)"
  PAUSE_ON_EXIT=0 ./install.sh --no-pause
fi

if command -v ss >/dev/null 2>&1 && ss -ltn | awk '{print $4}' | grep -q ":${SERVER_PORT}$"; then
  listener_pid="$(ss -ltnp 2>/dev/null | awk "/:${SERVER_PORT} / {print \\$0}" | sed -n 's/.*pid=\\([0-9]*\\).*/\\1/p' | head -n 1)"
  if curl -sS --max-time 2 "http://127.0.0.1:${SERVER_PORT}/health" >/dev/null 2>&1; then
    [ -n "$listener_pid" ] && echo "$listener_pid" > server.pid
    echo "Server 已在執行：PID ${listener_pid:-unknown}"
    echo "Server URL: http://127.0.0.1:${SERVER_PORT}"
    echo "LAN URL: http://$(hostname -I 2>/dev/null | awk '{print $1}'):${SERVER_PORT}"
    exit 0
  fi
  echo "Port ${SERVER_PORT} 已被占用，但不是可辨識的 Evidence Server。"
  echo "請先找出占用程序，或修改 .env 的 SERVER_PORT。"
  exit 1
fi

. .venv/bin/activate

SSL_ARGS=""
SSL_SCHEME="http"
if [ -n "${SSL_CERT_FILE:-}" ] && [ -n "${SSL_KEY_FILE:-}" ]; then
  if [ ! -f "$SSL_CERT_FILE" ] || [ ! -f "$SSL_KEY_FILE" ]; then
    echo "SSL 憑證不存在，正在自動產生自簽憑證..."
    openssl req -x509 -newkey rsa:2048 -nodes \
      -keyout "$SSL_KEY_FILE" -out "$SSL_CERT_FILE" \
      -days 365 -subj "/CN=Evidence-First-Server" 2>/dev/null
    echo "已產生自簽憑證（有效期 365 天）。"
  fi
  SSL_ARGS="--ssl-keyfile=$SSL_KEY_FILE --ssl-certfile=$SSL_CERT_FILE"
  SSL_SCHEME="https"
fi

setsid uvicorn app.main:app --host "$SERVER_HOST" --port "$SERVER_PORT" $SSL_ARGS > logs/server.log 2>&1 < /dev/null &
echo $! > server.pid
sleep 1
kill -0 "$(cat server.pid)" 2>/dev/null

LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo ""
echo "============================================"
echo "  Evidence-First Server 已啟動"
echo "============================================"
echo ""
echo "  本機位址：${SSL_SCHEME}://127.0.0.1:${SERVER_PORT}"
if [ -n "$LAN_IP" ]; then
  echo "  區域網路：${SSL_SCHEME}://${LAN_IP}:${SERVER_PORT}"
  echo ""
  echo "  ★★★ 請將以下位址告訴使用 User 端的人："
  echo "       ${SSL_SCHEME}://${LAN_IP}:${SERVER_PORT}"
else
  echo "  無法偵測區域網路 IP，請手動確認。"
fi
echo ""
echo "  API 文件：${SSL_SCHEME}://127.0.0.1:${SERVER_PORT}/docs"
echo "  資料位置：${SERVER_DATA_DIR:-./server_data}"
echo "  Log 路徑：$BASE_DIR/logs/server.log"
echo "  工作佇列：最多同時處理 ${MAX_CONCURRENT_FILE_JOBS:-1} 個檔案"
if [ -n "${SSL_CERT_FILE:-}" ]; then
  echo "  HTTPS：已啟用（自簽憑證）"
fi
echo "============================================"
