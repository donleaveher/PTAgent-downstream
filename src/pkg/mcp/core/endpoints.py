from __future__ import annotations

from typing import Optional, Tuple
from urllib.parse import urlparse


def split_mcp_endpoints(endpoint: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    将配置的 endpoint 拆成：

    - Streamable HTTP MCP URL（供 MCP 客户端）
    - Provider 控制面 WebSocket URL

    支持：

    - ``http(s)://host:port/mcp`` 或 ``http(s)://host:port``（自动补 ``/mcp``）
    - ``ws(s)://host:port`` → 推导 ``http(s)://host:port/mcp`` 与 ``ws(s)://host:port/provider``
    """
    if not endpoint:
        return None, None
    raw = endpoint.strip()
    parsed = urlparse(raw)
    if parsed.scheme in {"ws", "wss"}:
        http_scheme = "http" if parsed.scheme == "ws" else "https"
        netloc = parsed.netloc or ""
        http_url = f"{http_scheme}://{netloc}/mcp"
        ws_url = f"{parsed.scheme}://{netloc}/provider"
        return http_url, ws_url

    if parsed.scheme in {"http", "https"}:
        path = (parsed.path or "").rstrip("/")
        if not path or path == "/":
            base = f"{parsed.scheme}://{parsed.netloc}"
            http_url = f"{base}/mcp"
        elif path.endswith("/mcp"):
            http_url = raw.split("#")[0]
        else:
            http_url = f"{parsed.scheme}://{parsed.netloc}{path}/mcp"
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        ws_url = f"{ws_scheme}://{parsed.netloc}/provider"
        return http_url, ws_url

    return None, None


def http_base_from_mcp_url(http_mcp_url: str) -> str:
    """``http://host:port/mcp`` → ``http://host:port``"""
    p = urlparse(http_mcp_url)
    return f"{p.scheme}://{p.netloc}"


def resolve_listen_address(http_mcp_endpoint: Optional[str]) -> tuple[str, int]:
    if not http_mcp_endpoint:
        return ("0.0.0.0", 8765)
    parsed = urlparse(http_mcp_endpoint)
    if parsed.scheme not in {"http", "https"}:
        return ("0.0.0.0", 8765)
    host = parsed.hostname or "0.0.0.0"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return (host, port)


def resolve_ws_host_port(endpoint: Optional[str] = None) -> tuple[str, int]:
    """从 ``http`` 或 ``ws`` 类 endpoint 解析监听 host/port。"""
    http_e, _ = split_mcp_endpoints(endpoint or "http://127.0.0.1:8765/mcp")
    if not http_e:
        return ("0.0.0.0", 8765)
    return resolve_listen_address(http_e)
