from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from fastmcp.client import Client
from mcp.types import CallToolResult

from pkg.mcp.core.endpoints import split_mcp_endpoints

from .errors import MCPError
from .types import ToolInfo


def _meta_category_group(item: Any) -> tuple[str, str]:
    """从 MCP ``Tool`` 读取 ``_meta.ptagent.toolCategory`` / ``toolGroup``。"""
    meta = getattr(item, "meta", None)
    if meta is None and hasattr(item, "model_dump"):
        dump = item.model_dump(by_alias=True)
        meta = dump.get("_meta") or dump.get("meta")
    if not isinstance(meta, dict):
        return "", ""
    pt = meta.get("ptagent")
    if not isinstance(pt, dict):
        return "", ""
    return (
        str(pt.get("toolCategory") or "").strip(),
        str(pt.get("toolGroup") or "").strip(),
    )


def _success_content_text(raw: CallToolResult) -> str:
    """成功调用时，从 content 块拼接文本（部分 Broker 不填 structuredContent）。"""
    parts: List[str] = []
    for block in raw.content or []:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(str(text))
    return "\n".join(parts).strip()


def _normalize_success_result(raw: CallToolResult) -> Dict[str, Any]:
    """统一为 dict：优先 structuredContent，否则解析 content 文本为 JSON，再否则包装为 rawText。"""
    sc = raw.structuredContent
    if isinstance(sc, dict):
        return dict(sc)
    if isinstance(sc, list):
        return {"items": sc}
    if sc is not None and not isinstance(sc, (dict, list)):
        return {"value": sc}
    txt = _success_content_text(raw)
    if not txt:
        return {"empty": True, "hint": "工具返回成功但无文本与 structuredContent"}
    try:
        parsed = json.loads(txt)
        if isinstance(parsed, dict):
            return parsed
        return {"result": parsed}
    except json.JSONDecodeError:
        return {"rawText": txt}


def _call_tool_error_text(raw: CallToolResult) -> str:
    """从 MCP ``CallToolResult`` 取出可读错误文本（``isError`` 时常带在 ``content`` 里）。"""
    parts: List[str] = []
    for block in raw.content or []:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(str(text))
    return " ".join(parts).strip()


class MCPClient:
    """
    连接 Broker：列出工具、调用工具（Streamable HTTP MCP）。

    - 同步：``list_tools`` / ``call_tool``
    - 异步：``list_tools_async`` / ``call_tool_async``
    """

    def __init__(self, endpoint: str) -> None:
        if not endpoint or not str(endpoint).strip():
            raise MCPError("必须传入非空 endpoint")
        self._endpoint = endpoint

    def _http_mcp_url(self) -> str:
        http_url, _ = split_mcp_endpoints(self._endpoint)
        if not http_url:
            raise MCPError(f"无法解析 MCP 地址: {self._endpoint!r}")
        return http_url

    def list_tools(self) -> List[ToolInfo]:
        return asyncio.run(self.list_tools_async())

    async def list_tools_async(self) -> List[ToolInfo]:
        http_url = self._http_mcp_url()
        try:
            async with Client(http_url) as cli:
                tools = await cli.list_tools()
        except Exception as exc:  # noqa: BLE001
            raise MCPError(f"列出工具失败: {exc}") from exc

        out: List[ToolInfo] = []
        for item in tools:
            name = str(item.name or "")
            if not name:
                continue
            inp = item.inputSchema
            if hasattr(inp, "model_dump"):
                inp = inp.model_dump(exclude_none=True)
            if not isinstance(inp, dict):
                inp = {}
            osc = item.outputSchema
            if hasattr(osc, "model_dump"):
                osc = osc.model_dump(exclude_none=True)
            tc, tg = _meta_category_group(item)
            out.append(
                ToolInfo(
                    name=name,
                    description=str(item.description or ""),
                    input_schema=inp,
                    output_schema=dict(osc) if isinstance(osc, dict) else None,
                    tool_category=tc,
                    tool_group=tg,
                )
            )
        return out

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return asyncio.run(self.call_tool_async(name, arguments or {}))

    async def call_tool_async(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        http_url = self._http_mcp_url()
        try:
            async with Client(http_url) as cli:
                raw = await cli.call_tool_mcp(name, arguments)
        except Exception as exc:  # noqa: BLE001
            raise MCPError(f"调用工具 {name!r} 失败: {exc}") from exc
        if raw.isError:
            detail = _call_tool_error_text(raw)
            if not detail and isinstance(raw.structuredContent, dict):
                detail = str(raw.structuredContent)
            msg = f"工具 {name!r} 返回错误"
            if detail:
                msg = f"{msg}: {detail}"
            raise MCPError(msg)
        return _normalize_success_result(raw)


__all__ = ["MCPClient"]
