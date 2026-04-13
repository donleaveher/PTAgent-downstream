"""
middleware 包：HTTP / 应用中间件（认证、日志、追踪等）。

约定：
- 具体中间件实现放在子模块中（如 `http`）；
- 此处只做简单聚合和对外 re-export。
"""

from __future__ import annotations

from fastapi import FastAPI

from .http import register_http_middlewares


def register_middlewares(app: FastAPI) -> None:
    """统一注册所有中间件。"""

    register_http_middlewares(app)


__all__ = ["register_middlewares"]

