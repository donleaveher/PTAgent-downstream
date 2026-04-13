"""MCP 专用配置。

嵌套在 :class:`config.settings.AppSettings` 的 ``mcp`` 字段中加载；环境变量前缀为 ``PTAGENT_MCP__``（例如 ``PTAGENT_MCP__ENDPOINT``）。

业务代码若只关心 MCP，可使用 :func:`get_mcp_settings` 获取当前 ``MCPSettings`` 实例。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MCPSettings(BaseModel):
    """MCP Broker / 客户端 / Provider 共用配置。"""

    endpoint: str = Field(
        ...,
        description=(
            "MCP Streamable HTTP 地址（如 http://host:port/mcp），"
            "或 ws://host:port（将推导 HTTP 与 Provider WS）"
        ),
    )
    mode: str = Field(
        "default",
        description="MCP 运行模式（如 default / debug / offline），对应请求头 mcpMode。",
    )
    version: str = Field(
        "1.0.0",
        description="MCP 协议/实现版本，对应请求头 mcpVersion。",
    )
    auto_start_subprocess: bool = Field(
        True,
        description="后端启动时是否自动拉起 MCP Broker 子进程。",
    )
    subprocess_pid_file: str = Field(
        "/tmp/ptagent-mcp-server.pid",
        description="MCP 子进程守护使用的 PID 文件路径。",
    )
    discovery_service_name: str = Field(
        "mcp-server",
        description="进程内发现中心注册用的服务名。",
    )


def get_mcp_settings() -> MCPSettings:
    """返回当前应用配置中的 MCP 段（与 ``get_settings().mcp`` 等价）。"""

    from .settings import get_settings

    return get_settings().mcp


__all__ = ["MCPSettings", "get_mcp_settings"]
