"""
实验向导「物种检索」用例：经 MCP 调 Broker 上已注册工具；失败则兜底占位。

MCP 返回 dict 的解析见 ``pkg.mcp.tool_result_normalize``。
"""

from __future__ import annotations

import os
from typing import Any

from config import get_mcp_settings
from pkg.mcp.client_pool import get_mcp_client
from pkg.mcp.errors import MCPError
from pkg.mcp.tool_result_normalize import normalize_mcp_tool_dict_to_results

_DEFAULT_TOOL = "search_organism_taxonomy"


def _fallback_results(query: str, limit: int, reason: str) -> dict[str, Any]:
    return {
        "query": query,
        "size": min(max(1, int(limit)), 100),
        "results": [
            {
                "taxonId": 9606,
                "scientificName": "Homo sapiens",
                "commonName": "Human",
                "rank": "species",
                "mnemonic": "",
                "lineage": [],
            }
        ],
        "_mcpFallback": True,
        "_mcpFallbackReason": reason[:300],
    }


def taxonomy_search_for_ui(query: str, *, limit: int = 10) -> dict[str, Any]:
    q = (query or "").strip()
    if not q:
        return _fallback_results("", limit, "empty query")

    try:
        mcp = get_mcp_settings()
    except Exception as exc:  # noqa: BLE001
        return _fallback_results(q, limit, f"settings: {exc}")

    endpoint = (mcp.endpoint or "").strip()
    if not endpoint:
        return _fallback_results(q, limit, "PTAGENT_MCP_SETTINGS__ENDPOINT 未配置")

    tool = (os.environ.get("PTAGENT_UNIPROT_TAXONOMY_MCP_TOOL") or _DEFAULT_TOOL).strip() or _DEFAULT_TOOL
    lim = min(max(1, int(limit)), 100)
    args: dict[str, Any] = {"query": q, "limit": lim}

    try:
        client = get_mcp_client(endpoint)
        raw = client.call_tool(tool, args)
    except (MCPError, OSError, ValueError, TypeError) as exc:
        return _fallback_results(q, lim, str(exc))
    except Exception as exc:  # noqa: BLE001
        return _fallback_results(q, lim, str(exc))

    if not isinstance(raw, dict):
        return _fallback_results(q, lim, "MCP 返回非 object")

    return normalize_mcp_tool_dict_to_results(raw, query=q, size=lim)


__all__ = ["taxonomy_search_for_ui"]
