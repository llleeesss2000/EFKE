#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/..
echo "更新 Server Python 依賴與資料庫 schema"
. .venv/bin/activate
python -m pip install -r requirements-server.txt
python - <<'PY'
from app.main import init_db
init_db()
print("schema 已同步")
PY

read -p "按 Enter 關閉此視窗..."
