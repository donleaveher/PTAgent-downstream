#!/usr/bin/env bash
# 单独启动 MCP Broker（阻塞）。当 PTAGENT_MCP_SETTINGS__AUTO_START_SUBPROCESS=false 时需手动先起本进程。
# 监听地址需与 .env 中 PTAGENT_MCP_SETTINGS__ENDPOINT 一致（默认可用 http://127.0.0.1:8765/mcp）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"

HOST="${MCP_BROKER_HOST:-0.0.0.0}"
PORT="${MCP_BROKER_PORT:-8765}"

echo "[PTAgent] 启动 MCP Broker — ${HOST}:${PORT}（请保证 PTAGENT_MCP_SETTINGS__ENDPOINT 指向 http://127.0.0.1:${PORT}/mcp 或等价地址）"
exec python -c "from pkg.mcp import MCPService; MCPService().run(host='${HOST}', port=${PORT})"
