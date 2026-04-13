#!/usr/bin/env bash
# 启动 FastAPI 后端（入口：src/main.py → main:app）
# 用法：在项目根目录 ./scripts/run-backend.sh
# 环境变量：PORT（默认 8000）；需配置 .env 中的 PTAGENT_*（含 PTAGENT_MCP__ENDPOINT）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"

PORT="${PORT:-8000}"

echo "[PTAgent] 启动后端 uvicorn main:app — http://0.0.0.0:${PORT}"
echo "[PTAgent] MCP 控制台（若已挂载）：http://0.0.0.0:${PORT}/mcp-admin/"
exec uvicorn main:app --host 0.0.0.0 --port "$PORT" --reload
