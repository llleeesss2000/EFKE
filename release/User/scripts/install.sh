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
  echo
  if [ "$code" -eq 0 ]; then
    echo "User 安裝完成。"
    echo "所在位置：$BASE_DIR"
    echo "下一步：./start.sh"
  else
    echo "User 安裝失敗，請查看上方錯誤訊息。"
  fi
  if [ "$PAUSE_ON_EXIT" = "1" ] && [ -t 0 ]; then
    read -r -p "按 Enter 關閉此視窗..."
  fi
  exit "$code"
}
trap finish EXIT

echo "== Evidence-First User 一鍵安裝 =="
python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("需要 Python 3.10 以上")
print(f"Python：{sys.version.split()[0]}")
PY

test -f .env || cp .env.example .env
mkdir -p user_data logs
test -w user_data || { echo "user_data 不可寫"; exit 1; }

if [ -d .venv ]; then
  if [ ! -x .venv/bin/python ] || [ ! -x .venv/bin/uvicorn ] || ! .venv/bin/python - <<'PY' >/dev/null 2>&1
import fastapi, uvicorn, httpx
PY
  then
    backup=".venv.broken.$(date +%Y%m%d_%H%M%S)"
    echo "偵測到 venv 已損壞或路徑失效，移到 $backup"
    mv .venv "$backup"
  fi
fi

if [ ! -d .venv ]; then
  echo "建立新的 User venv：$BASE_DIR/.venv"
  python3 -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-user.txt
