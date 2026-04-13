from __future__ import annotations

from typing import Iterable, List

from pkg.mcp.client import MCPClient
from pkg.mcp.types import ToolInfo

from ..contracts import AgentSpec


def filter_tools_for_agent(spec: AgentSpec, tools: Iterable[ToolInfo]) -> List[ToolInfo]:
    """先按 ``mcp_categories`` 过滤，再按 ``mcp_tool_allowlist`` 按名收窄。"""
    cats = spec.mcp_categories
    if cats is None:
        out = list(tools)
    elif not cats:
        out = []
    else:
        out = []
        for t in tools:
            tc = (t.tool_category or "").strip()
            if tc in cats:
                out.append(t)

    allow = spec.mcp_tool_allowlist
    if allow is None:
        return out
    if not allow:
        return []
    return [t for t in out if t.name in allow]


class McpToolScope:
    """封装「某 endpoint 下、某 Agent 可见」的工具视图与调用。"""

    def __init__(self, client: MCPClient, spec: AgentSpec) -> None:
        self._client = client
        self._spec = spec
        self._filtered: List[ToolInfo] | None = None

    def list_tools(self) -> List[ToolInfo]:
        if self._filtered is None:
            self._filtered = filter_tools_for_agent(self._spec, self._client.list_tools())
        return self._filtered

    def invalidate_cache(self) -> None:
        self._filtered = None

    def call_tool(self, name: str, arguments: dict) -> dict:
        allowed = {t.name for t in self.list_tools()}
        if name not in allowed:
            raise PermissionError(
                f"Agent {self._spec.key!r} 无权调用工具 {name!r}（不在允许的 category/allowlist 内）"
            )
        return self._client.call_tool(name, arguments)
