from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware


def register_http_middlewares(app: FastAPI) -> None:
    """注册 HTTP 相关中间件。"""

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


__all__ = ["register_http_middlewares"]

