#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/..
. .venv/bin/activate
python - <<'PY'
from app.main import rebuild
print(rebuild()["message"])
print("重建工作已執行")
PY
