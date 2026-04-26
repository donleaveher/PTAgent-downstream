from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from .config import BrokerConfig
from .discovery import heartbeat
from .relay_tool import BrokerRelayTool


@dataclass
class RegisteredTool:
    """Broker 内已登记的一条工具元数据（由 Provider 上报）。"""

    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]]
    owner_provider_id: str
    tool_category: str = ""
    tool_group: str = ""


class ToolBroker:
    """
    核心引擎：维护 Provider 连接、工具注册表，以及经 FastMCP 暴露的动态工具。

    一般通过 :class:`MCPBroker` 使用；仅在需要直接操作 ``FastMCP`` 或注册表时使用本类。
    """

    def __init__(self, config: BrokerConfig) -> None:
        self._config = config
        dup = config.on_duplicate_tools
        self._mcp = FastMCP(
            config.name,
            instructions=config.instructions,
            on_duplicate=dup,
        )
        self._registry_lock = Lock()
        self._tool_registry: Dict[str, RegisteredTool] = {}
        self._provider_connections: Dict[str, WebSocket] = {}
        self._provider_heartbeats: Dict[str, float] = {}
        self._ws_provider_ids: Dict[int, str] = {}
        self._pending_calls: Dict[str, asyncio.Future] = {}

    @property
    def mcp(self) -> FastMCP:
        return self._mcp

    @property
    def config(self) -> BrokerConfig:
        return self._config

    def list_registered_tools(self) -> List[RegisteredTool]:
        with self._registry_lock:
            return list(self._tool_registry.values())

    def get_tool_by_name(self, name: str) -> Optional[RegisteredTool]:
        with self._registry_lock:
            return self._tool_registry.get(name)

    def _cleanup_provider(self, provider_id: str) -> None:
        with self._registry_lock:
            to_remove = [n for n, t in self._tool_registry.items() if t.owner_provider_id == provider_id]
            for name in to_remove:
                self._tool_registry.pop(name, None)
            self._provider_connections.pop(provider_id, None)
            self._provider_heartbeats.pop(provider_id, None)
        for name in to_remove:
            try:
                self._mcp.remove_tool(name)
            except Exception:  # noqa: BLE001
                pass

    def _cleanup_stale_providers(self) -> None:
        now = time.time()
        ttl = self._config.provider_ttl_seconds
        with self._registry_lock:
            stale = [pid for pid, ts in self._provider_heartbeats.items() if now - ts > ttl]
        for pid in stale:
            self._cleanup_provider(pid)

    def _make_error_response(self, id_value: Any, code: int, message: str) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": id_value, "error": {"code": code, "message": message}}

    def _handle_initialize(self, request: Dict[str, Any]) -> Dict[str, Any]:
        req_id = request.get("id")
        c = self._config
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": c.name, "version": c.version},
            },
        }

    def _register_tools_with_fastmcp(self, parsed_tools: List[RegisteredTool]) -> None:
        for t in parsed_tools:
            rt = BrokerRelayTool(
                broker=self,
                tool_name=t.name,
                description=t.description,
                input_schema=t.input_schema,
                output_schema=t.output_schema,
                tool_category=t.tool_category,
                tool_group=t.tool_group,
            )
            self._mcp.add_tool(rt)

    def _handle_provider_register(self, request: Dict[str, Any], ws: WebSocket) -> Dict[str, Any]:
        req_id = request.get("id")
        params = request.get("params") or {}
        provider_id = str(params.get("providerId") or "").strip()
        tools = params.get("tools") or []
        if not provider_id:
            return self._make_error_response(req_id, -32602, "Invalid params: providerId is required")
        if not isinstance(tools, list):
            return self._make_error_response(req_id, -32602, "Invalid params: tools must be list")

        parsed_tools: List[RegisteredTool] = []
        for item in tools:
            if not isinstance(item, dict):
                return self._make_error_response(req_id, -32602, f"Invalid tool item: {item!r}")
            name = str(item.get("name") or "").strip()
            description = str(item.get("description") or "").strip()
            input_schema = item.get("inputSchema") or {"type": "object", "properties": {}}
            output_schema = item.get("outputSchema")
            if not name:
                return self._make_error_response(req_id, -32602, "Invalid tool: name is required")
            if not description:
                return self._make_error_response(req_id, -32602, f"Invalid tool {name!r}: description is required")
            if not isinstance(input_schema, dict):
                return self._make_error_response(req_id, -32602, f"Invalid tool {name!r}: inputSchema must be object")
            if output_schema is not None and not isinstance(output_schema, dict):
                return self._make_error_response(
                    req_id, -32602, f"Invalid tool {name!r}: outputSchema must be object or null"
                )
            tc = str(item.get("toolCategory") or "").strip()
            tg = str(item.get("toolGroup") or "").strip()
            parsed_tools.append(
                RegisteredTool(
                    name=name,
                    description=description,
                    input_schema=dict(input_schema),
                    output_schema=dict(output_schema) if output_schema is not None else None,
                    owner_provider_id=provider_id,
                    tool_category=tc,
                    tool_group=tg,
                )
            )

        with self._registry_lock:
            for tool_name in list(self._tool_registry.keys()):
                if self._tool_registry[tool_name].owner_provider_id == provider_id:
                    old = self._tool_registry.pop(tool_name)
                    try:
                        self._mcp.remove_tool(old.name)
                    except Exception:  # noqa: BLE001
                        pass
            for tool in parsed_tools:
                existing = self._tool_registry.get(tool.name)
                if existing is not None and existing.owner_provider_id != provider_id:
                    return self._make_error_response(req_id, -32602, f"Tool name conflict: {tool.name!r}")
            for tool in parsed_tools:
                self._tool_registry[tool.name] = tool
            self._provider_connections[provider_id] = ws
            self._provider_heartbeats[provider_id] = time.time()
            self._ws_provider_ids[id(ws)] = provider_id

        self._register_tools_with_fastmcp(parsed_tools)

        return {"jsonrpc": "2.0", "id": req_id, "result": {"registered": [tool.name for tool in parsed_tools]}}

    def _handle_provider_heartbeat(self, request: Dict[str, Any]) -> Dict[str, Any]:
        req_id = request.get("id")
        params = request.get("params") or {}
        provider_id = str(params.get("providerId") or "").strip()
        if not provider_id:
            return self._make_error_response(req_id, -32602, "Invalid params: providerId is required")
        with self._registry_lock:
            known = provider_id in self._provider_connections
            if known:
                self._provider_heartbeats[provider_id] = time.time()
        return {"jsonrpc": "2.0", "id": req_id, "result": {"knownProvider": known}}

    def _handle_provider_unregister(self, request: Dict[str, Any]) -> Dict[str, Any]:
        req_id = request.get("id")
        params = request.get("params") or {}
        provider_id = str(params.get("providerId") or "").strip()
        if not provider_id:
            return self._make_error_response(req_id, -32602, "Invalid params: providerId is required")
        self._cleanup_provider(provider_id)
        return {"jsonrpc": "2.0", "id": req_id, "result": {"unregistered": provider_id}}

    async def invoke_provider(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        with self._registry_lock:
            tool = self._tool_registry.get(tool_name)
            if tool is None:
                raise RuntimeError(f"Unknown tool: {tool_name}")
            provider_ws = self._provider_connections.get(tool.owner_provider_id)
        if provider_ws is None:
            raise RuntimeError(f"Tool provider offline: {tool.owner_provider_id}")
        if provider_ws.client_state != WebSocketState.CONNECTED:
            raise RuntimeError(f"Tool provider socket not connected: {tool.owner_provider_id}")

        relay_id = f"relay-{uuid.uuid4()}"
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        with self._registry_lock:
            self._pending_calls[relay_id] = future

        timeout = self._config.tool_invocation_timeout_seconds
        try:
            await provider_ws.send_text(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": relay_id,
                        "method": "provider/invoke",
                        "params": {"toolName": tool_name, "arguments": arguments},
                    },
                    ensure_ascii=False,
                )
            )
            try:
                structured_content = await asyncio.wait_for(future, timeout=timeout)
            except asyncio.TimeoutError:
                raise RuntimeError("Tool provider timeout") from None
        finally:
            with self._registry_lock:
                self._pending_calls.pop(relay_id, None)

        if isinstance(structured_content, dict) and structured_content.get("error"):
            return structured_content
        return structured_content

    def _handle_provider_invoke_response(self, request: Dict[str, Any]) -> None:
        req_id = request.get("id")
        if not isinstance(req_id, str):
            return
        with self._registry_lock:
            fut = self._pending_calls.get(req_id)
        if fut is None or fut.done():
            return
        if isinstance(request.get("error"), dict):
            fut.set_result({"error": request["error"]})
            return
        result = request.get("result")
        if isinstance(result, dict):
            fut.set_result(result)
        else:
            fut.set_result({"result": result})

    async def _dispatch_ws_json(self, request: Dict[str, Any], ws: WebSocket) -> Optional[Dict[str, Any]]:
        if "id" in request and "method" not in request and ("result" in request or "error" in request):
            self._handle_provider_invoke_response(request)
            return None

        method = request.get("method")
        if not method or "id" not in request:
            return None
        if method == "initialize":
            return self._handle_initialize(request)
        if method == "provider/register":
            return self._handle_provider_register(request, ws)
        if method == "provider/heartbeat":
            return self._handle_provider_heartbeat(request)
        if method == "provider/unregister":
            return self._handle_provider_unregister(request)
        return self._make_error_response(request.get("id"), -32601, f"Method not found: {method}")

    async def _provider_connection_loop(self, ws: WebSocket) -> None:
        sid = self._config.discovery_service_id
        try:
            while True:
                if sid:
                    heartbeat(sid)
                self._cleanup_stale_providers()
                try:
                    raw = await ws.receive_text()
                except WebSocketDisconnect:
                    break
                try:
                    request = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send_text(json.dumps(self._make_error_response(None, -32700, "Parse error"), ensure_ascii=False))
                    continue
                if not isinstance(request, dict):
                    await ws.send_text(
                        json.dumps(
                            self._make_error_response(None, -32600, "Invalid Request: JSON object required"),
                            ensure_ascii=False,
                        )
                    )
                    continue
                response = await self._dispatch_ws_json(request, ws)
                if response is not None:
                    await ws.send_text(json.dumps(response, ensure_ascii=False))
        finally:
            provider_id = self._ws_provider_ids.pop(id(ws), None)
            if provider_id:
                self._cleanup_provider(provider_id)


def build_broker_asgi_app(broker: ToolBroker) -> Any:
    base = broker.mcp.http_app(path=broker.config.mcp_http_path)
    prov_path = broker.config.provider_ws_path

    async def provider_ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        await broker._provider_connection_loop(ws)

    from starlette.routing import WebSocketRoute

    base.routes.insert(0, WebSocketRoute(prov_path, endpoint=provider_ws_endpoint))
    return base


__all__ = [
    "RegisteredTool",
    "ToolBroker",
    "build_broker_asgi_app",
]
