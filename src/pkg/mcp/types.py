from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ToolInfo:
    """对外可见的工具描述（列表/编排用）。"""

    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None
    #: 注册时上报，经 MCP ``Tool._meta.ptagent`` 回传（供 Admin 分组）
    tool_category: str = ""
    tool_group: str = ""


__all__ = ["ToolInfo"]
