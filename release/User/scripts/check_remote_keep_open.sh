#!/usr/bin/env bash
cd "$(dirname "$0")/..
test -f .env || cp .env.example .env
. .env

echo "== 遠端連線檢查 =="
echo "Server API：${SERVER_API_URL}"
echo "LLM API：${LLM_BASE_URL}"
echo

server_health="${SERVER_API_URL%/}/health"
if curl -sS --max-time 5 "$server_health" >/tmp/evidence_server_check.json 2>/tmp/evidence_server_check.err; then
  echo "Server API：可連線"
  cat /tmp/evidence_server_check.json
  echo
else
  echo "Server API：連線失敗"
  cat /tmp/evidence_server_check.err
  echo
  echo "請到 192.168.31.36 那台 GX10 檢查："
  echo "1. cd 到 release/Server"
  echo "2. 執行 ./status_keep_open.sh"
  echo "3. 確認 SERVER_HOST=0.0.0.0、SERVER_PORT=8000"
  echo "4. 確認防火牆允許 TCP 8000"
  echo "5. 確認可從 GX10 本機打開 http://127.0.0.1:8000/docs"
fi

echo
ollama_url="${LLM_BASE_URL%/v1}"
if curl -sS --max-time 5 "${ollama_url%/}/api/tags" >/tmp/evidence_llm_check.json 2>/tmp/evidence_llm_check.err; then
  echo "LLM / Ollama：可連線"
  python3 - <<'PY' 2>/dev/null || cat /tmp/evidence_llm_check.json
import json
data=json.load(open('/tmp/evidence_llm_check.json'))
for item in data.get('models', [])[:8]:
    print('-', item.get('name'))
PY
else
  echo "LLM / Ollama：連線失敗"
  cat /tmp/evidence_llm_check.err
fi

echo
read -r -p "按 Enter 關閉這個視窗..."
