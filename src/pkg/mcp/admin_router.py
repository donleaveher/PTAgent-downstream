"""MCP 可视化与管理：HTTP API + 多页静态界面（见 ``admin/``）。"""

from __future__ import annotations

import asyncio
import mimetypes
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from config import get_mcp_settings
from frontend.paths import MCP as _MCP_FRONTEND_DIR
from pkg.mcp.mcp_framework.endpoints import split_mcp_endpoints

from .client_pool import get_mcp_client
from .conventions import load_conventions_document
from .errors import MCPError

_ADMIN_DIR = _MCP_FRONTEND_DIR


def _tool_rows_for_admin(tools: list[Any]) -> list[dict[str, Any]]:
    """将 :class:`~pkg.mcp.types.ToolInfo` 转为 Admin 表格行（类别来自注册 ``@tool(category=..., group=...)``）。"""
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
                "categoryTitle": tc or "未分类",
                "groupLabel": tg or "未分组",
            }
        )
    return rows


def _catalog_from_tool_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """由当前工具列表推导一份 ``tool_catalog`` 形制的摘要（来源为 MCP 注册 meta，非独立 JSON 文件）。"""
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


def _serve_admin_html(filename: str) -> FileResponse:
    path = (_ADMIN_DIR / filename).resolve()
    if not path.is_file() or not str(path).startswith(str(_ADMIN_DIR.resolve())):
        raise HTTPException(status_code=404, detail="MCP admin page not found")
    return FileResponse(path, media_type="text/html; charset=utf-8")


_ASSETS_ROOT = (_ADMIN_DIR / "assets").resolve()


def _serve_admin_static(rel: str) -> FileResponse:
    if ".." in rel or rel.startswith("/"):
        raise HTTPException(status_code=404, detail="Not found")
    target = (_ASSETS_ROOT / rel).resolve()
    if not str(target).startswith(str(_ASSETS_ROOT)) or not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    media = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media)


mcp_admin_router = APIRouter(prefix="/mcp-admin", tags=["mcp-admin"])


def _client():
    return get_mcp_client(get_mcp_settings().endpoint)


class CallToolBody(BaseModel):
    name: str = Field(..., min_length=1, description="工具名称")
    arguments: dict[str, Any] = Field(default_factory=dict, description="JSON 参数对象")


@mcp_admin_router.get("", include_in_schema=False)
def mcp_admin_redirect_slash() -> RedirectResponse:
    return RedirectResponse(url="/mcp-admin/", status_code=307)


@mcp_admin_router.get("/", response_class=HTMLResponse, include_in_schema=False)
def mcp_admin_index() -> FileResponse:
    return _serve_admin_html("index.html")


@mcp_admin_router.get("/tools", response_class=HTMLResponse, include_in_schema=False)
def mcp_admin_tools_page() -> FileResponse:
    return _serve_admin_html("tools.html")


@mcp_admin_router.get("/fields", response_class=HTMLResponse, include_in_schema=False)
def mcp_admin_fields_page() -> FileResponse:
    return _serve_admin_html("fields.html")


@mcp_admin_router.get("/debug", response_class=HTMLResponse, include_in_schema=False)
def mcp_admin_debug_page() -> FileResponse:
    return _serve_admin_html("debug.html")


@mcp_admin_router.get("/static/{path:path}", include_in_schema=False)
def mcp_admin_static(path: str) -> FileResponse:
    return _serve_admin_static(path)


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
    """跨工具字段命名约定（由宿主模块提供，见 ``load_conventions_document``）。"""
    return load_conventions_document()


@mcp_admin_router.get("/api/tool-catalog")
async def mcp_admin_tool_catalog() -> dict[str, Any]:
    """由当前 Broker 已注册工具推导分组摘要（与 ``@tool(category=..., group=...)`` / MCP ``meta`` 一致）。"""
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
async def mcp_admin_call_tool(body: CallToolBody) -> dict[str, Any]:
    try:
        result = await _client().call_tool_async(body.name, body.arguments)
    except MCPError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "result": result}


__all__ = ["mcp_admin_router"]
