"""
response 包：统一响应模型与包装逻辑。

职责：
- 定义标准的 API 响应结构（成功 / 失败）；
- 提供便捷的包装函数；
- 提供 FastAPI 异常处理注册函数，将 AppError 映射为统一错误响应。
"""

from __future__ import annotations

from typing import Any, Generic, Optional, TypeVar

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from errmsg import AppError


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: str
    message: str
    data: Optional[T] = None


class ErrorResponse(BaseModel):
    code: str
    message: str
    detail: Optional[str] = None


def ok(data: T, code: str = "OK", message: str = "success") -> ApiResponse[T]:
    return ApiResponse[T](code=code, message=message, data=data)


def error_from_app_error(exc: AppError) -> ErrorResponse:
    info = exc.info
    return ErrorResponse(code=info.code, message=info.message, detail=info.detail)


def register_exception_handlers(app: FastAPI) -> None:
    """
    注册全局异常处理，将 AppError 统一映射为 HTTP 400 错误响应。
    """

    @app.exception_handler(AppError)
    async def app_error_handler(  # type: ignore[override]
        request: Request,
        exc: AppError,
    ) -> JSONResponse:
        err = error_from_app_error(exc)
        return JSONResponse(
            status_code=400,
            content=err.model_dump(),
        )


__all__ = [
    "ApiResponse",
    "ErrorResponse",
    "ok",
    "error_from_app_error",
    "register_exception_handlers",
]
