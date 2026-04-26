"""pkg.mcp.core — 可嵌入的 MCP Broker 与传输内核。

对外建议只使用：

- :class:`MCPBroker` — 组合 ASGI 应用与可选阻塞运行
- :class:`BrokerConfig` — 行为与路径配置
- :class:`RegisteredTool` — 工具元数据类型

进阶：:class:`ToolBroker`、:func:`build_broker_asgi_app`。

进程内服务发现：:class:`MCPDiscoveryCenter`、:class:`MCPService`。

Endpoint 解析：:func:`split_mcp_endpoints`、:func:`resolve_listen_address` 等。
"""

from importlib.metadata import PackageNotFoundError, version

from .app import MCPBroker
from .broker import RegisteredTool, ToolBroker, build_broker_asgi_app
from .config import BrokerConfig
from .discovery import (
    MCPDiscoveryCenter,
    MCPService,
    discover_endpoint,
    get_service,
    heartbeat,
    list_services,
    register_service,
    unregister_service,
)
from .endpoints import (
    http_base_from_mcp_url,
    resolve_listen_address,
    resolve_ws_host_port,
    split_mcp_endpoints,
)

try:
    __version__ = version("mcp-framework")
except PackageNotFoundError:
    __version__ = "0.2.0"

__all__ = [
    "BrokerConfig",
    "MCPBroker",
    "MCPDiscoveryCenter",
    "MCPService",
    "RegisteredTool",
    "ToolBroker",
    "__version__",
    "build_broker_asgi_app",
    "discover_endpoint",
    "get_service",
    "heartbeat",
    "http_base_from_mcp_url",
    "list_services",
    "register_service",
    "resolve_listen_address",
    "resolve_ws_host_port",
    "split_mcp_endpoints",
    "unregister_service",
]
