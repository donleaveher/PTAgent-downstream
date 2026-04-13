"""
errmsg 包：统一错误码与错误信息管理。

约定：
- 使用 `msg(code, message, detail)` 生成统一格式的错误字符串；
- 使用 `AppError` 作为应用层/领域层的统一异常类型，在接口层映射为 HTTP 错误。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class ErrorInfo:
    code: str
    message: str
    detail: Optional[str] = None


def msg(code: str, message: str, detail: Optional[str] = None) -> str:
    """
    生成统一格式的错误消息字符串。

    示例：
    - msg("PIPELINE_EMPTY", "pipeline 必须包含至少一个节点")
      -> "[PIPELINE_EMPTY] pipeline 必须包含至少一个节点"
    """

    if detail:
        return f"[{code}] {message}: {detail}"
    return f"[{code}] {message}"


class AppError(Exception):
    """
    应用层统一异常类型，携带错误码与错误信息。
    """

    def __init__(self, code: str, message: str, detail: Optional[str] = None) -> None:
        self.info = ErrorInfo(code=code, message=message, detail=detail)
        super().__init__(msg(code, message, detail))


__all__ = ["ErrorInfo", "msg", "AppError"]
