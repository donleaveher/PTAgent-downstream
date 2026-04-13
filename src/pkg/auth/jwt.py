from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

import jwt
from jwt import InvalidTokenError

from config import AppSettings
from domain import RunContext


@dataclass
class RequestMeta:
    """
    领域层的请求元信息。

    - 从 HTTP 请求头或其他调用方上下文中提取；
    - 用于统一传递 requestId / apiVersion / mcp 版本等。
    """

    request_id: str
    timestamp: int
    api_version: str
    mcp_version: str
    mcp_mode: str

    user_id: Optional[str] = None
    raw_jwt: Optional[str] = None
    jwt_claims: Optional[Dict[str, Any]] = None


class RequestValidationError(Exception):
    """请求头缺失或非法时抛出的异常。"""


def _get_header(headers: Mapping[str, str], key: str) -> Optional[str]:
    """大小写不敏感地获取 header。"""

    lower_key = key.lower()
    for k, v in headers.items():
        if k.lower() == lower_key:
            return v
    return None


def parse_jwt_token(token: str, settings: AppSettings) -> Dict[str, Any]:
    """
    解析并校验 JWT。

    当前假设使用对称密钥 HS256（或 settings.jwt 中指定的算法），
    并校验 iss / exp / iat 等标准字段。
    """

    try:
        claims = jwt.decode(
            token,
            key=settings.jwt.secret_key,
            algorithms=[settings.jwt.algorithm],
            issuer=settings.jwt.issuer,
            leeway=settings.jwt.leeway_seconds,
        )
    except InvalidTokenError as exc:
        raise RequestValidationError(f"Invalid JWT token: {exc}") from exc

    return claims


def extract_request_meta_from_headers(
    headers: Mapping[str, str],
    settings: AppSettings,
) -> RequestMeta:
    """
    从请求头中抽取标准字段并校验 JWT。

    约定的请求头：
    - requestId
    - timestamp（整数秒）
    - apiVersion
    - mcpVersion
    - mcpMode
    - Authorization: Bearer <JWT>
    """

    request_id = _get_header(headers, "requestId")
    timestamp_raw = _get_header(headers, "timestamp")
    api_version = _get_header(headers, "apiVersion") or settings.api_version
    mcp_version = _get_header(headers, "mcpVersion") or settings.mcp.version
    mcp_mode = _get_header(headers, "mcpMode") or settings.mcp.mode
    auth_header = _get_header(headers, "Authorization")

    if not request_id:
        raise RequestValidationError("Missing header: requestId")
    if not timestamp_raw:
        raise RequestValidationError("Missing header: timestamp")

    try:
        timestamp = int(timestamp_raw)
    except ValueError as exc:
        raise RequestValidationError("Invalid header timestamp, must be int") from exc

    raw_jwt = None
    claims: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None

    if auth_header:
        if not auth_header.startswith("Bearer "):
            raise RequestValidationError("Authorization header must start with 'Bearer '")
        raw_jwt = auth_header[len("Bearer ") :].strip()
        if not raw_jwt:
            raise RequestValidationError("Authorization header contains empty token")

        claims = parse_jwt_token(raw_jwt, settings=settings)
        user_id = claims.get("userId")  # type: ignore[assignment]

    return RequestMeta(
        request_id=request_id,
        timestamp=timestamp,
        api_version=api_version,
        mcp_version=mcp_version,
        mcp_mode=mcp_mode,
        user_id=user_id,
        raw_jwt=raw_jwt,
        jwt_claims=claims,
    )


def build_run_context_from_request_meta(
    meta: RequestMeta,
    *,
    run_id: str,
    config: Optional[Mapping[str, Any]] = None,
    project_id: Optional[str] = None,
    sample_id: Optional[str] = None,
) -> RunContext:
    """
    将 RequestMeta 映射为 RunContext，便于在应用层统一构造内核上下文。
    """

    return RunContext(
        run_id=run_id,
        request_id=meta.request_id,
        api_version=meta.api_version,
        mcp_version=meta.mcp_version,
        mcp_mode=meta.mcp_mode,
        project_id=project_id,
        sample_id=sample_id,
        user_id=meta.user_id,
        config=config or {},
    )

