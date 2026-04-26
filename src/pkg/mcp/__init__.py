"""
MCP 对外接口：

- :class:`MCPService` — 在本进程或通过子进程启动 Broker
- :class:`MCPClient` — 列出/调用工具（同步与异步 API 均可）
- :class:`ToolProvider` + :func:`tool` — 继承并实现工具方法（实现模块位于 ``pkg.mcp.core.provider``）

Broker / JSON-RPC 传输见 ``pkg.mcp.core``。对外部 Tool Provider 进程无代码依赖（由独立仓库部署并连同一 Broker）。
"""

from .client import MCPClient
from .core.provider import ToolProvider, tool
from .errors import MCPError
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
