from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional


@dataclass
class BrokerConfig:
    """
    Broker 行为与路径配置。

    对外 MCP 使用 FastMCP 的 Streamable HTTP（默认路径 ``/mcp``）；
    Provider 控制面为独立 WebSocket（默认 ``/provider``）。
    """

    name: str = "mcp-broker"
    version: str = "0.2.0"
    instructions: str = (
        "MCP broker: remote providers register tools over WebSocket; "
        "clients use standard MCP over HTTP."
    )
    mcp_http_path: str = "/mcp"
    provider_ws_path: str = "/provider"
    provider_ttl_seconds: float = 90.0
    tool_invocation_timeout_seconds: float = 20.0
    on_duplicate_tools: Literal["replace", "warn", "error", "ignore"] = "replace"
    #: 进程内发现：为本 broker 注册一条服务记录；为 None 时不写入发现、连接循环也不打 discovery 心跳
    discovery_service_id: Optional[str] = "mcp-broker-local"
    discovery_service_name: str = "mcp-broker"
    #: 写入发现元数据的协议标签
    discovery_protocol: str = "http+mcp"
    #: 随发现一起写入的额外字段
    discovery_metadata: Dict[str, Any] = field(default_factory=dict)
