"""Agent Studio：轻量 API + 静态资源（页面重定向到 PTAgent）。"""

from __future__ import annotations

import mimetypes
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from frontend.paths import AGENT_STUDIO
from pkg.mcp.resource_payload import mcp_tools_payload

_ADMIN_DIR = AGENT_STUDIO
_ASSETS = (_ADMIN_DIR / "assets").resolve()

agent_studio_router = APIRouter(prefix="/agent-studio", tags=["agent-studio"])


def _serve_html(name: str) -> FileResponse:
    path = (_ADMIN_DIR / name).resolve()
    root = _ADMIN_DIR.resolve()
    if not path.is_file() or not str(path).startswith(str(root)):
        raise HTTPException(status_code=404, detail="页面不存在")
    return FileResponse(path, media_type="text/html; charset=utf-8")


def _serve_asset(rel: str) -> FileResponse:
    if ".." in rel or rel.startswith("/"):
        raise HTTPException(status_code=404, detail="Not found")
    target = (_ASSETS / rel).resolve()
    if not str(target).startswith(str(_ASSETS)) or not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    media = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media)


@agent_studio_router.get("", include_in_schema=False)
def agent_studio_slash() -> RedirectResponse:
    return RedirectResponse(url="/agent-studio/", status_code=307)


@agent_studio_router.get("/", response_class=HTMLResponse, include_in_schema=False)
def agent_studio_index() -> RedirectResponse:
    return RedirectResponse(url="/ptagent-admin/agents", status_code=302)


@agent_studio_router.get("/static/{path:path}", include_in_schema=False)
def agent_studio_static(path: str) -> FileResponse:
    return _serve_asset(path)


@agent_studio_router.get("/api/overview", include_in_schema=True)
def agent_studio_overview() -> dict[str, Any]:
    out = mcp_tools_payload()
    out["note"] = "Agent Studio 已合并到 /ptagent-admin；请改用 /ptagent-admin/api/mcp-resources。"
    return out
