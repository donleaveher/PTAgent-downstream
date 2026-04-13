"""校验逻辑；执行请用 :mod:`pkg.agent.runner` 与 :mod:`pkg.agent.team`（统一路径）。"""

from __future__ import annotations

from typing import Any

from config import get_mcp_settings

from pkg.mcp.client_pool import get_mcp_client

from ._internal.mcp_scope import McpToolScope
from .contracts import AgentSpec


def validate_agent(
    spec: AgentSpec,
    *,
    endpoint: str | None = None,
) -> dict[str, Any]:
    """静态校验 + 列出解析后的工具（需 Broker 可达）。"""
    ep = endpoint or get_mcp_settings().endpoint
    warnings: list[str] = []
    if not (spec.system_prompt or "").strip():
        warnings.append("system_prompt 为空，模型可能行为不稳定")
    if spec.mcp_categories is not None and len(spec.mcp_categories) == 0:
        warnings.append("mcp_categories 为空集合：类别层面不会绑定任何 MCP 工具")
    if spec.mcp_tool_allowlist is not None and len(spec.mcp_tool_allowlist) == 0:
        warnings.append("mcp_tool_allowlist 为空：不允许调用任何工具")
    try:
        client = get_mcp_client(ep)
        scope = McpToolScope(client, spec)
        tools = scope.list_tools()
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "mcpEndpoint": ep,
            "error": str(exc),
            "tools": [],
            "warnings": warnings,
        }
    if not tools and spec.mcp_categories is not None and len(spec.mcp_categories) > 0:
        warnings.append("当前类别下无可用工具，请检查 Broker 注册或类别名")
    return {
        "ok": True,
        "mcpEndpoint": ep,
        "tools": [
            {
                "name": t.name,
                "tool_category": t.tool_category,
                "tool_group": t.tool_group,
            }
            for t in tools
        ],
        "warnings": warnings,
    }
