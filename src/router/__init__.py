"""
router 包：HTTP 路由（FastAPI APIRouter）。

约定：
- 子模块如 ``ptagent_admin``、``mcp_admin``、``home`` 仅做路径与入参绑定，复杂逻辑在 ``application`` 或 ``pkg``；
- 请求体模型放在 ``model.http``；统一响应包装见 ``response``。
"""

from __future__ import annotations

from fastapi import FastAPI

from .agent_studio import agent_studio_router
from .data_plane import data_plane_router
from .mcp_admin import mcp_admin_router
from .ptagent_admin import ptagent_admin_router


def register_routes(app: FastAPI) -> None:
    """将所有 HTTP 路由挂载到应用上。"""

    app.include_router(mcp_admin_router)
    app.include_router(agent_studio_router)
    app.include_router(data_plane_router)
    app.include_router(ptagent_admin_router)


__all__ = [
    "register_routes",
    "agent_studio_router",
    "data_plane_router",
    "mcp_admin_router",
    "ptagent_admin_router",
]
