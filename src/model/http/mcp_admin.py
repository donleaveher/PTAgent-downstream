"""MCP 管理台 HTTP 请求体（与路由解耦，供 ``router.mcp_admin`` 使用）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class McpCallToolBody(BaseModel):
    name: str = Field(..., min_length=1, description="工具名称")
    arguments: dict[str, Any] = Field(default_factory=dict, description="JSON 参数对象")


class McpToolArgPresetsStoredBody(BaseModel):
    """仅替换数据库层；与内置合并由 GET 返回的 merged 反映。"""

    stored: dict[str, dict[str, Any]] = Field(default_factory=dict, description="工具名 -> 示例 arguments")


class McpToolArgPresetUpsertBody(BaseModel):
    name: str = Field(..., min_length=1, description="工具名称")
    arguments: dict[str, Any] = Field(default_factory=dict, description="将写入数据库的示例参数")


__all__ = [
    "McpCallToolBody",
    "McpToolArgPresetUpsertBody",
    "McpToolArgPresetsStoredBody",
]
