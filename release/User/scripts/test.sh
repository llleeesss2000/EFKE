#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
. .venv/bin/activate
python - <<'PY'
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
assert client.get("/").status_code == 200
assert client.get("/api/config").status_code == 200
print("User 測試通過：首頁與設定 API 可用")
PY

if [ -t 0 ]; then
  read -r -p "按 Enter 關閉此視窗..."
fi
