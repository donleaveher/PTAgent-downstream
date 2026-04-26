"""Agent Studio 兼容 API（静态已迁出；请用边缘入口访问 UI）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from application.mcp_resource_payload import mcp_tools_payload

agent_studio_router = APIRouter(prefix="/agent-studio", tags=["agent-studio"])


@agent_studio_router.get("/api/overview", include_in_schema=True)
def agent_studio_overview() -> dict[str, Any]:
    out = mcp_tools_payload()
    out["note"] = "Agent Studio 已合并到 /ptagent-admin；请改用 /ptagent-admin/api/mcp-resources。"
    return out


__all__ = ["agent_studio_router"]
