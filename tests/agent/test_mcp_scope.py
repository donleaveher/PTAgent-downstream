"""MCP 按类别过滤与 AgentSpec 行为单元测试（无网络）。"""

from __future__ import annotations

import pytest

from pkg.agent._internal.mcp_scope import McpToolScope, filter_tools_for_agent
from pkg.agent.contracts import AgentSpec, categories
from pkg.mcp.types import ToolInfo


def _tool(name: str, cat: str) -> ToolInfo:
    return ToolInfo(
        name=name,
        description="",
        input_schema={"type": "object", "properties": {}},
        tool_category=cat,
        tool_group=f"{cat}.g",
    )


def test_filter_by_category() -> None:
    tools = [_tool("a", "basic"), _tool("b", "spectral")]
    spec = AgentSpec(key="x", mcp_categories=categories("basic"))
    got = filter_tools_for_agent(spec, tools)
    assert [t.name for t in got] == ["a"]


def test_filter_none_means_all() -> None:
    spec = AgentSpec(key="x", mcp_categories=None)
    tools = [_tool("a", "basic")]
    assert len(filter_tools_for_agent(spec, tools)) == 1


def test_filter_empty_set_denies() -> None:
    spec = AgentSpec(key="x", mcp_categories=frozenset())
    tools = [_tool("a", "basic")]
    assert filter_tools_for_agent(spec, tools) == []


def test_allowlist_narrows_after_category() -> None:
    tools = [_tool("a", "basic"), _tool("b", "basic")]
    spec = AgentSpec(
        key="x",
        mcp_categories=categories("basic"),
        mcp_tool_allowlist=frozenset({"a"}),
    )
    got = filter_tools_for_agent(spec, tools)
    assert [t.name for t in got] == ["a"]


def test_mcp_scope_call_tool_denies() -> None:
    class _Fake:
        def list_tools(self):
            return [_tool("only", "basic")]

        def call_tool(self, name: str, arguments: dict) -> dict:
            return {"ok": True}

    spec = AgentSpec(key="a", mcp_categories=categories("spectral"))
    scope = McpToolScope(_Fake(), spec)  # type: ignore[arg-type]
    assert scope.list_tools() == []
    with pytest.raises(PermissionError):
        scope.call_tool("only", {})
