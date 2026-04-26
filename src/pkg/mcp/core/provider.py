from __future__ import annotations

import asyncio
import inspect
import json
import os
import sys
import uuid
import collections.abc
from typing import Any, Callable, Dict, List, Optional, get_args, get_origin, get_type_hints

import websockets
from websockets.exceptions import WebSocketException

from pkg.mcp.core.endpoints import split_mcp_endpoints
from pkg.mcp.errors import MCPError


def _broker_reconnect_interval() -> float:
    """Broker 不可用时，固定间隔（秒）后重试；默认 ``10``，可用 ``PTAGENT_MCP_BROKER_RECONNECT_INTERVAL`` 覆盖。"""
    sec = float(os.environ.get("PTAGENT_MCP_BROKER_RECONNECT_INTERVAL", "10.0"))
    return max(0.1, sec)


def tool(
    func: Optional[Callable[..., Any]] = None,
    *,
    description: str = "",
    category: str = "",
    group: str = "",
) -> Any:
    """
    标记子类中的方法为 MCP 工具（同步或 async 均可）。

    支持 ``@tool`` / ``@tool(description=\"...\")`` / ``@tool(category=\"...\", group=\"...\")``。
    ``category`` / ``group`` 会随 ``provider/register`` 上报，Broker 写入 MCP ``Tool`` 的 meta，供 Admin 分组展示。
    """

    def _mark(
        fn: Callable[..., Any],
        desc: str,
        cat: str,
        grp: str,
    ) -> Callable[..., Any]:
        setattr(fn, "__mcp_tool_description__", (desc or (fn.__doc__ or "")).strip())
        setattr(fn, "__mcp_tool_category__", (cat or "").strip())
        setattr(fn, "__mcp_tool_group__", (grp or "").strip())
        return fn

    if func is not None:
        return _mark(func, description, category, group)
    return lambda fn: _mark(fn, description, category, group)


def _unwrap_optional(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin is type(None):
        return str
    if origin is not None:
        args = [a for a in get_args(annotation) if a is not type(None)]
        if args:
            return args[0]
    return annotation


def _json_schema_for_annotation(ann: Any) -> Dict[str, Any] | None:
    """将 typing 注解映射为 JSON Schema 片段；无法识别时返回 None。"""
    if ann in (dict,):
        return {"type": "object", "additionalProperties": True}
    origin = get_origin(ann)
    args = get_args(ann)
    type_map = {
        int: {"type": "integer"},
        float: {"type": "number"},
        str: {"type": "string"},
        bool: {"type": "boolean"},
    }
    if origin is not None and origin in (list, List, collections.abc.Sequence):
        if len(args) == 1:
            inner = args[0]
            if inner is int:
                return {"type": "array", "items": {"type": "integer"}}
            if inner is str:
                return {"type": "array", "items": {"type": "string"}}
            if inner is float:
                return {"type": "array", "items": {"type": "number"}}
        return {"type": "array"}
    if ann in type_map:
        return type_map[ann]
    return None


def _schema_for_function(fn: Callable[..., Any]) -> Dict[str, Any]:
    sig = inspect.signature(fn)
    try:
        hints = get_type_hints(fn)
    except Exception:  # noqa: BLE001
        hints = {}
    properties: Dict[str, Any] = {}
    required: List[str] = []
    type_map = {
        int: {"type": "integer"},
        float: {"type": "number"},
        str: {"type": "string"},
        bool: {"type": "boolean"},
    }
    has_var_keyword = False
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            has_var_keyword = True
            continue
        ann = hints.get(name, str)
        ann = _unwrap_optional(ann)
        if ann is dict or get_origin(ann) is dict:
            properties[name] = {"type": "object", "additionalProperties": True}
        elif (js := _json_schema_for_annotation(ann)) is not None:
            properties[name] = js
        elif ann in type_map:
            properties[name] = type_map[ann]
        else:
            properties[name] = {"type": "string"}
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": bool(has_var_keyword),
    }


class _JsonRpcOverWs:
    def __init__(self, ws: Any) -> None:
        self._ws = ws
        self._pending: Dict[str, asyncio.Future[Any]] = {}

    async def request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        req_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[req_id] = fut
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            payload["params"] = params
        await self._ws.send(json.dumps(payload, ensure_ascii=False))
        try:
            return await asyncio.wait_for(fut, timeout=60.0)
        finally:
            self._pending.pop(req_id, None)

    def complete_from_message(self, msg: Dict[str, Any]) -> bool:
        req_id = msg.get("id")
        if not isinstance(req_id, str) or req_id not in self._pending:
            return False
        fut = self._pending.pop(req_id)
        if msg.get("error"):
            err = msg["error"]
            msg_txt = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            if not fut.done():
                fut.set_exception(MCPError(msg_txt))
        else:
            res = msg.get("result")
            if not isinstance(res, dict):
                res = {}
            if not fut.done():
                fut.set_result(res)
        return True


class ToolProvider:
    """
    工具开发者继承此类，用 ``@tool`` 标注方法，调用 ``run()`` 向 Broker 注册并保持连接。

    只实现业务方法即可；协议、心跳、``provider/invoke`` 由基类处理。

    **连接**：Broker 未监听或连接断开时，会**固定间隔无限重试**（默认每 10 秒一次，可用
    ``PTAGENT_MCP_BROKER_RECONNECT_INTERVAL`` 配置，单位秒）。
    """

    provider_label: str = "tools"

    def __init__(self, endpoint: str, *, heartbeat_seconds: float = 10.0) -> None:
        if not endpoint or not str(endpoint).strip():
            raise MCPError("必须传入非空 endpoint")
        self._endpoint = endpoint
        self._heartbeat_seconds = heartbeat_seconds
        self._provider_id = f"provider-{uuid.uuid4()}"
        self._handlers: Dict[str, Callable[..., Any]] = {}
        self._tools_payload: List[Dict[str, Any]] = []
        self._collect_tools()

    def _collect_tools(self) -> None:
        for _, method in inspect.getmembers(self, predicate=inspect.ismethod):
            fn = getattr(method, "__func__", method)
            if not getattr(fn, "__mcp_tool_description__", None):
                continue
            name = method.__name__
            desc = getattr(fn, "__mcp_tool_description__", "") or name
            tc = getattr(fn, "__mcp_tool_category__", "") or ""
            tg = getattr(fn, "__mcp_tool_group__", "") or ""
            self._handlers[name] = method
            item: Dict[str, Any] = {
                "name": name,
                "description": desc,
                "inputSchema": _schema_for_function(method),
                "outputSchema": {"type": "object", "additionalProperties": True},
            }
            if tc:
                item["toolCategory"] = tc
            if tg:
                item["toolGroup"] = tg
            self._tools_payload.append(item)

    def _ws_url(self) -> str:
        _, ws = split_mcp_endpoints(self._endpoint)
        if not ws:
            raise MCPError(f"无法从 endpoint 推导 Provider WebSocket: {self._endpoint!r}")
        return ws

    def run(self) -> None:
        asyncio.run(self._run_async())

    async def _run_connected_session(self, ws: Any) -> None:
        rpc = _JsonRpcOverWs(ws)

        async def pump() -> None:
            async for raw in ws:
                msg = json.loads(raw)
                if not isinstance(msg, dict):
                    continue
                if rpc.complete_from_message(msg):
                    continue
                if msg.get("method") == "provider/invoke":
                    await self._on_invoke(ws, msg)

        pump_task = asyncio.create_task(pump())
        hb_task: Optional[asyncio.Task[None]] = None
        try:
            await rpc.request("initialize", {"protocolVersion": "2024-11-05"})
            await rpc.request(
                "provider/register",
                {
                    "providerId": self._provider_id,
                    "providerName": self.provider_label,
                    "tools": self._tools_payload,
                },
            )

            async def heartbeat() -> None:
                while True:
                    await asyncio.sleep(self._heartbeat_seconds)
                    try:
                        await rpc.request("provider/heartbeat", {"providerId": self._provider_id})
                    except Exception:  # noqa: BLE001
                        pass

            hb_task = asyncio.create_task(heartbeat())
            await pump_task
        finally:
            if hb_task is not None:
                hb_task.cancel()
                try:
                    await hb_task
                except asyncio.CancelledError:
                    pass
            pump_task.cancel()
            try:
                await pump_task
            except asyncio.CancelledError:
                pass

    async def _run_async(self) -> None:
        ws_url = self._ws_url()
        interval = _broker_reconnect_interval()
        warned = False
        while True:
            try:
                async with websockets.connect(ws_url, max_size=None) as ws:
                    if warned:
                        print(f"[mcp-tool] 已连接 Broker {ws_url!r}（{self.provider_label}）", file=sys.stderr)
                        warned = False
                    await self._run_connected_session(ws)
            except asyncio.CancelledError:
                raise
            except (OSError, WebSocketException) as exc:
                if not warned:
                    print(
                        f"[mcp-tool] 无法连接 Broker {ws_url!r}（{self.provider_label}）: {exc}；"
                        f"每 {interval:.1f}s 重试一次…",
                        file=sys.stderr,
                    )
                    warned = True
                await asyncio.sleep(interval)

    async def _on_invoke(self, ws: Any, msg: Dict[str, Any]) -> None:
        req_id = msg.get("id")
        params = msg.get("params") or {}
        name = str(params.get("toolName") or "")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        try:
            handler = self._handlers.get(name)
            if handler is None:
                raise MCPError(f"未知工具: {name}")
            if inspect.iscoroutinefunction(handler):
                result = await handler(**arguments)
            else:
                result = handler(**arguments)
            if not isinstance(result, dict):
                result = {"value": result}
            out: Dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "result": result}
        except Exception as exc:  # noqa: BLE001
            out = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": str(exc)},
            }
        await ws.send(json.dumps(out, ensure_ascii=False))


__all__ = ["ToolProvider", "tool"]
