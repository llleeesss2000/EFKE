#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/..
. .venv/bin/activate
python -m pip install -r requirements-user.txt
echo "User 端已更新"
