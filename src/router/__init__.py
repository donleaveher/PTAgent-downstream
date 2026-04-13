"""
router 包：HTTP 路由定义（FastAPI 路由集合）。

约定：
- 产品路由放在本包子模块（如 ``ptagent_admin``、``agent_studio``）；
- 与 ``pkg.*`` 可复用库代码分离。
"""

from __future__ import annotations

from fastapi import FastAPI

from pkg.mcp.admin_router import mcp_admin_router

from .agent_studio import agent_studio_router
from .ptagent_admin import ptagent_admin_router


def register_routes(app: FastAPI) -> None:
    """将所有 HTTP 路由挂载到应用上。"""

    app.include_router(mcp_admin_router)
    app.include_router(agent_studio_router)
    app.include_router(ptagent_admin_router)


__all__ = ["register_routes", "agent_studio_router", "ptagent_admin_router"]
