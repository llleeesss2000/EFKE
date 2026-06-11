#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/..
if [ "${1:-}" = "" ]; then
  echo "用法：./restore.sh /path/to/evidence_backup_xxx.tar.gz"
  exit 1
fi
. .venv/bin/activate
python - "$1" <<'PY'
import sys
from app.main import restore
print(restore(sys.argv[1])["message"])
PY
