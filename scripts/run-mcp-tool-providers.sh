#!/usr/bin/env bash
# 可选：转调到「外部 MCP Tool Provider 仓库」自带的启动脚本。
# PTAgent 主仓不依赖、也不内置具体工具实现；仅需 Broker 已运行且 endpoint 一致。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOL_ROOT="${PTAGENT_MCP_TOOL_ROOT:-${PTAGENT_MCP_ROOT:-}}"
if [[ -z "${TOOL_ROOT}" || ! -d "${TOOL_ROOT}" ]]; then
  echo "未设置有效的工具仓路径。请 export PTAGENT_MCP_TOOL_ROOT=/path/to/your-mcp-tools-repo" >&2
  echo "（或兼容旧名 PTAGENT_MCP_ROOT），再执行本脚本；或直接进入该仓按其 README 启动 Provider。" >&2
  exit 1
fi
SUB="${TOOL_ROOT}/scripts/run-mcp-tool-providers.sh"
if [[ -x "$SUB" ]]; then
  exec "$SUB"
fi
if [[ -f "$SUB" ]]; then
  exec bash "$SUB"
fi
echo "在 ${TOOL_ROOT}/scripts/ 下未找到可执行的 run-mcp-tool-providers.sh，请查阅该仓文档。" >&2
exit 1
