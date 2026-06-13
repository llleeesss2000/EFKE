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
    echo "Server 安裝完成。"
    echo "所在位置：$BASE_DIR"
    echo "下一步：./start.sh"
  else
    echo "Server 安裝失敗，請查看上方錯誤訊息。"
  fi
  if [ "$PAUSE_ON_EXIT" = "1" ] && [ -t 0 ]; then
    read -r -p "按 Enter 關閉此視窗..."
  fi
  exit "$code"
}
trap finish EXIT

echo "== Evidence-First Server 一鍵安裝 =="
python3 - <<'PY'
import shutil, sys
if sys.version_info < (3, 10):
    raise SystemExit("需要 Python 3.10 以上")
free = shutil.disk_usage(".").free // (1024**3)
if free < 10:
    raise SystemExit("MinerU 與模型需要較多空間；磁碟可用空間少於 10GB，請先清理空間")
print(f"Python：{sys.version.split()[0]}")
print(f"磁碟可用空間：{free} GB")
PY

test -f .env || cp .env.example .env
mkdir -p server_data/originals server_data/derived server_data/backups logs
test -w server_data || { echo "server_data 不可寫"; exit 1; }

if [ -d .venv ]; then
  if [ ! -x .venv/bin/python ] || [ ! -x .venv/bin/uvicorn ] || ! .venv/bin/python - <<'PY' >/dev/null 2>&1
import fastapi, uvicorn, pydantic_core
PY
  then
    backup=".venv.broken.$(date +%Y%m%d_%H%M%S)"
    echo "偵測到 venv 已損壞或路徑失效，移到 $backup"
    mv .venv "$backup"
  fi
fi

if [ ! -d .venv ]; then
  echo "建立新的 Server venv：$BASE_DIR/.venv"
  python3 -m venv .venv
fi

. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --timeout 120 uv || true
python -m pip install -r requirements-server.txt
python -m pip install --timeout 120 -U mineru
python -m pip install --timeout 120 -U "torch>=2.6.0" torchvision
python -m uv pip install -U "transformers>=4.57.3,<5.0.0" safetensors tokenizers || python -m pip install --timeout 120 -U "transformers>=4.57.3,<5.0.0" safetensors tokenizers
python -m uv pip install ftfy || python -m pip install --timeout 120 -U ftfy
python -m uv pip install hf_transfer || python -m pip install --timeout 120 -U hf_transfer
HF_HUB_ENABLE_HF_TRANSFER=1 MINERU_MODEL_SOURCE=huggingface python -m mineru.cli.models_download -s huggingface -m pipeline

if command -v cargo >/dev/null 2>&1; then
  echo "編譯 Rust 加速模組..."
  cd rust-tools && cargo build --release 2>&1 | tail -3 && cd ..
  echo "Rust 工具編譯完成"
else
  echo "未安裝 Rust，跳過 Rust 加速模組（可選）"
fi

python - <<'PY'
from app.main import init_db
init_db()
print("資料庫初始化完成")
PY
