"""MCP 相关异常。"""


class MCPError(RuntimeError):
    """MCP 调用或工具侧错误。"""


__all__ = ["MCPError"]
