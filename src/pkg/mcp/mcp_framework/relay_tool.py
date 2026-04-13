from __future__ import annotations

from typing import Any, Dict, Optional

from fastmcp.exceptions import ToolError
from fastmcp.tools.base import Tool, ToolResult
from pydantic import PrivateAttr


def _normalize_input_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    if not schema:
        return {"type": "object", "properties": {}, "additionalProperties": False}
    out = dict(schema)
    if "type" not in out:
        out["type"] = "object"
    if out.get("type") == "object" and "properties" not in out:
        out["properties"] = {}
    return out


def _normalize_output_schema(schema: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if schema is None:
        return None
    out = dict(schema)
    if "type" not in out:
        out["type"] = "object"
    return out


class BrokerRelayTool(Tool):
    """将 tools/call 转发到已连接的 Provider WebSocket。"""

    KEY_PREFIX = "tool"

    # FastMCP ``Tool`` 基于 Pydantic（extra=forbid）；普通 ``self._x`` 会在 ``super().__init__`` 时被清掉，
    # 须用 PrivateAttr 保留 Broker 引用。
    _broker: Any = PrivateAttr()

    def __init__(
        self,
        *,
        broker: Any,
        tool_name: str,
        description: str,
        input_schema: Dict[str, Any],
        output_schema: Optional[Dict[str, Any]],
        tool_category: str = "",
        tool_group: str = "",
    ) -> None:
        meta: dict[str, Any] | None = None
        if tool_category or tool_group:
            meta = {
                "ptagent": {
                    "toolCategory": tool_category,
                    "toolGroup": tool_group,
                }
            }
        super().__init__(
            name=tool_name,
            description=description,
            parameters=_normalize_input_schema(input_schema),
            output_schema=_normalize_output_schema(output_schema),
            meta=meta,
        )
        self._broker = broker

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            payload = await self._broker.invoke_provider(self.name, arguments)
        except RuntimeError as exc:
            raise ToolError(str(exc)) from exc
        if isinstance(payload, dict) and payload.get("error"):
            err = payload["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise ToolError(msg)
        return self.convert_result(payload)
