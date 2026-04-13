#!/usr/bin/env bash
# 一键启动 registry 中配置的 MCP Tool Provider（多进程，每个 Provider 一条 WS 到 Broker）
# 不占额外监听端口；需先有 MCP Broker，且 PTAGENT_MCP__ENDPOINT 与之一致。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"

echo "[PTAgent] 启动 mcp_tools providers（默认见 mcp_tools/registry.py，可用 MCP_TOOLS_PROVIDERS 覆盖）..."
exec python -m mcp_tools.run_providers
