#!/usr/bin/env bash
# 启动 FastAPI 后端（入口：src/main.py → main:app）
# 用法：在项目根目录 ./scripts/run-backend.sh
# 环境变量：PORT（默认 8000）；需配置 .env 中的 PTAGENT_*（含 PTAGENT_MCP_SETTINGS__ENDPOINT）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
PY="${PTAGENT_PYTHON_SERVER:-${PTAGENT_VENV_SERVER:+$PTAGENT_VENV_SERVER/bin/python}}"
if [[ -n "${PY}" && -x "${PY}" ]]; then
  :
elif [[ -x "$REPO/env/server/bin/python" ]]; then
  PY="$REPO/env/server/bin/python"
else
  PY="python3"
fi

PORT="${PORT:-8000}"

echo "[PTAgent] uvicorn main:app — http://0.0.0.0:${PORT}  (API /docs；UI 用 PTAgent-frontend 边缘)"
# 若 PTAGENT_UVICORN_RELOAD=0 或 false 则适合 nohup 守护（不启用 --reload）
RELOAD=1
case "${PTAGENT_UVICORN_RELOAD:-1}" in
  0|false|False|no|NO) RELOAD=0 ;;
esac
if [ "$RELOAD" -eq 1 ]; then
  exec "$PY" -m uvicorn main:app --host 0.0.0.0 --port "$PORT" --reload
else
  exec "$PY" -m uvicorn main:app --host 0.0.0.0 --port "$PORT"
fi
