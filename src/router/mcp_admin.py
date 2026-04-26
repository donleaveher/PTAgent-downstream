"""MCP 管理 API（``/mcp-admin/api``）。静态页与资源由 ``PTAgent-frontend`` 边缘服务提供。"""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException

from application.mcp_tool_arg_presets import (
    merge_tool_arg_presets,
    replace_stored_tool_arg_presets,
    upsert_stored_tool_arg_preset,
)
from config import get_mcp_settings
from model.http.mcp_admin import (
    McpCallToolBody,
    McpToolArgPresetUpsertBody,
    McpToolArgPresetsStoredBody,
)
from pkg.mcp.client_pool import get_mcp_client
from pkg.mcp.conventions import load_conventions_document
from pkg.mcp.core.endpoints import split_mcp_endpoints
from pkg.mcp.errors import MCPError
from pkg.mcp.types import ToolInfo


def _tool_rows_for_admin(tools: list[ToolInfo]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for t in tools:
        d = asdict(t)
        tc = (d.get("tool_category") or "").strip()
        tg = (d.get("tool_group") or "").strip()
        rows.append(
            {
                "name": d["name"],
                "description": d["description"],
                "inputSchema": d["input_schema"],
                "outputSchema": d.get("output_schema"),
                "categoryId": tc,
                "groupId": tg,
                "categoryTitle": tc or "uncategorized",
                "groupLabel": tg or "ungrouped",
            }
        )
    return rows


def _catalog_from_tool_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    categories: dict[str, str] = {}
    groups: dict[str, Any] = {}
    tool_map: dict[str, Any] = {}
    for r in rows:
        cid = (r.get("categoryId") or "").strip()
        gid = (r.get("groupId") or "").strip()
        if cid:
            categories[cid] = r.get("categoryTitle") or cid
        if gid:
            groups[gid] = {"label": r.get("groupLabel") or gid, "category": cid}
        name = r.get("name") or ""
        if name and gid:
            tool_map[name] = {"group": gid}
    return {
        "version": 1,
        "schema": "mcp_tool_catalog_v1",
        "source": "mcp_tool_registration",
        "categories": categories,
        "groups": groups,
        "tools": tool_map,
    }


mcp_admin_router = APIRouter(prefix="/mcp-admin", tags=["mcp-admin"])


def _client():
    return get_mcp_client(get_mcp_settings().endpoint)


@mcp_admin_router.get("/api/overview")
async def mcp_admin_overview() -> dict[str, Any]:
    mcp = get_mcp_settings()
    http_u, ws_u = split_mcp_endpoints(mcp.endpoint)
    reachable = False
    last_error: str | None = None
    tool_count: int | None = None
    try:
        tools = await asyncio.wait_for(_client().list_tools_async(), timeout=15.0)
        reachable = True
        tool_count = len(tools)
    except asyncio.TimeoutError:
        last_error = "连接 MCP 超时（>15s）"
    except MCPError as exc:
        last_error = str(exc)
    except Exception as exc:  # noqa: BLE001
        last_error = str(exc)

    return {
        "endpoint": mcp.endpoint,
        "httpMcpUrl": http_u,
        "providerWsUrl": ws_u,
        "mode": mcp.mode,
        "version": mcp.version,
        "autoStartSubprocess": mcp.auto_start_subprocess,
        "subprocessPidFile": mcp.subprocess_pid_file,
        "reachable": reachable,
        "toolCount": tool_count,
        "lastError": last_error,
    }


@mcp_admin_router.get("/api/conventions")
def mcp_admin_conventions() -> dict[str, Any]:
    return load_conventions_document()


@mcp_admin_router.get("/api/tool-catalog")
async def mcp_admin_tool_catalog() -> dict[str, Any]:
    try:
        tools = await _client().list_tools_async()
    except MCPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    rows = _tool_rows_for_admin(tools)
    return _catalog_from_tool_rows(rows)


@mcp_admin_router.get("/api/tools")
async def mcp_admin_tools() -> dict[str, Any]:
    try:
        tools = await _client().list_tools_async()
    except MCPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    rows = _tool_rows_for_admin(tools)
    return {"tools": rows, "toolCatalog": _catalog_from_tool_rows(rows)}


@mcp_admin_router.post("/api/tools/call")
async def mcp_admin_call_tool(body: McpCallToolBody) -> dict[str, Any]:
    try:
        result = await _client().call_tool_async(body.name, body.arguments)
    except MCPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "result": result}


@mcp_admin_router.get("/api/tool-arg-presets")
def mcp_admin_tool_arg_presets_get() -> dict[str, Any]:
    merged, stored = merge_tool_arg_presets()
    return {
        "merged": merged,
        "stored": stored,
    }


@mcp_admin_router.put("/api/tool-arg-presets")
def mcp_admin_tool_arg_presets_put(body: McpToolArgPresetsStoredBody) -> dict[str, Any]:
    replace_stored_tool_arg_presets(body.stored)
    merged, stored = merge_tool_arg_presets()
    return {"ok": True, "merged": merged, "stored": stored}


@mcp_admin_router.post("/api/tool-arg-presets/item")
def mcp_admin_tool_arg_presets_upsert_one(body: McpToolArgPresetUpsertBody) -> dict[str, Any]:
    upsert_stored_tool_arg_preset(body.name, body.arguments)
    merged, stored = merge_tool_arg_presets()
    return {"ok": True, "merged": merged, "stored": stored}


__all__ = ["mcp_admin_router"]
