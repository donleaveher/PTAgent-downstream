"""Broker 工具列表摘要（供多处 HTTP / 重定向复用）。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from config import get_mcp_settings

from .client_pool import get_mcp_client


def mcp_tools_payload() -> dict[str, Any]:
    mcp = get_mcp_settings()
    err: str | None = None
    tools: list[dict[str, Any]] = []
    try:
        for t in get_mcp_client(mcp.endpoint).list_tools():
            tools.append(
                {
                    "name": t.name,
                    "description": t.description,
                    "tool_category": (t.tool_category or "").strip() or "未分类",
                    "tool_group": (t.tool_group or "").strip(),
                    "inputSchema": t.input_schema,
                    "outputSchema": t.output_schema,
                }
            )
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in tools:
        by_cat[row["tool_category"]].append(row)
    return {
        "mcpEndpoint": mcp.endpoint,
        "ok": err is None,
        "error": err,
        "toolCount": len(tools),
        "tools": tools,
        "toolsByCategory": {k: sorted([x["name"] for x in v]) for k, v in sorted(by_cat.items())},
        "byCategory": {k: v for k, v in sorted(by_cat.items())},
    }
