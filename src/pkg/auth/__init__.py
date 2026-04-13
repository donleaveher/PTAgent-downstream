"""
auth 包：统一的鉴权与请求元信息处理。

当前包含：
- jwt：JWT 解析、RequestMeta 构建以及 RunContext 映射
"""

from .jwt import (  # noqa: F401
    RequestMeta,
    RequestValidationError,
    build_run_context_from_request_meta,
    extract_request_meta_from_headers,
    parse_jwt_token,
)

