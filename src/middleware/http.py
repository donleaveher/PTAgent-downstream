from __future__ import annotations

import os

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware


def _cors_origins() -> list[str]:
    raw = os.environ.get("PTAGENT_CORS_ORIGINS", "").strip()
    if raw:
        return [x.strip() for x in raw.split(",") if x.strip()]
    return ["*"]


def register_http_middlewares(app: FastAPI) -> None:
    """注册 HTTP 相关中间件。"""

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


__all__ = ["register_http_middlewares"]

