"""
PTAgent 后端统一入口。

约定：
- 暴露 FastAPI 应用实例 `app`，供 uvicorn / gunicorn 等直接加载；
- 保持 main.py 作为整个后端的“单一入口点”（Python 模块路径：`main:app`）。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import get_mcp_settings
from frontend.paths import SHARED
from middleware import register_middlewares
from pkg.global_objects import close_global_objects
from pkg.mcp import MCPService
from response import register_exception_handlers
from router import register_routes


def _ensure_mcp_process() -> None:
    mcp = get_mcp_settings()
    if not mcp.auto_start_subprocess:
        return
    print(f"Starting MCP server with endpoint: {mcp.endpoint}")
    MCPService.ensure_subprocess(
        endpoint=mcp.endpoint,
        project_root=str(Path(__file__).parent.parent),
        pid_file=mcp.subprocess_pid_file,
    )


def create_backend_app() -> FastAPI:
    """
    创建后端主应用。

    挂载 MCP 管理台、PTAgent 管理端、Agent Studio 兼容路由等；后续可在此追加认证、任务等 API。
    """

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        _ensure_mcp_process()
        try:
            yield
        finally:
            # Release shared process-wide objects (MCP client pool etc.)
            close_global_objects()

    app = FastAPI(title="PTAgent Backend", version="0.1.0", lifespan=lifespan)

    # HTTP / 应用中间件
    register_middlewares(app)

    # 异常处理（如 AppError）
    register_exception_handlers(app)

    # HTTP 路由
    register_routes(app)

    if SHARED.is_dir():
        app.mount("/ui-static", StaticFiles(directory=str(SHARED)), name="ui_static")

    return app


# 供 `uvicorn main:app` 直接使用
app = create_backend_app()


if __name__ == "__main__":
    # 方便本地直接 `python -m main` 启动后端
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)