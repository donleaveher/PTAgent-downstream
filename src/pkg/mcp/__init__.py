"""
MCP 对外接口：

- :class:`MCPService` — 在本进程或通过子进程启动 Broker
- :class:`MCPClient` — 列出/调用工具（同步与异步 API 均可）
- :class:`ToolProvider` + :func:`tool` — 继承并实现工具方法

底层实现见 ``pkg.mcp.mcp_framework``。
"""

from .client import MCPClient
from .errors import MCPError
from .provider import ToolProvider, tool
from .service import MCPService
from .types import ToolInfo

from .client_pool import MCPClientPool, close_all_mcp_clients, get_mcp_client

__all__ = [
    "MCPClient",
    "MCPClientPool",
    "MCPError",
    "MCPService",
    "ToolInfo",
    "ToolProvider",
    "close_all_mcp_clients",
    "get_mcp_client",
    "tool",
]
