#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/..
. .venv/bin/activate
python - <<'PY'
from app.main import backup
print(backup()["backup_path"])
PY
