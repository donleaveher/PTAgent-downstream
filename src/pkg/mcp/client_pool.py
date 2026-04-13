from __future__ import annotations

from threading import Lock

from .client import MCPClient


class MCPClientPool:
    """按 endpoint 复用 ``MCPClient``（须显式传入 endpoint）。"""

    def __init__(self) -> None:
        self._lock = Lock()
        self._clients: dict[str, MCPClient] = {}

    def get_client(self, endpoint: str) -> MCPClient:
        if not endpoint or not str(endpoint).strip():
            raise ValueError("MCPClientPool.get_client 需要非空 endpoint")
        with self._lock:
            client = self._clients.get(endpoint)
            if client is not None:
                return client
            client = MCPClient(endpoint)
            self._clients[endpoint] = client
            return client

    def close_all(self) -> None:
        with self._lock:
            clients = list(self._clients.values())
            self._clients.clear()
        for client in clients:
            close = getattr(client, "close", None)
            if callable(close):
                close()


_GLOBAL_POOL = MCPClientPool()


def get_mcp_client(endpoint: str) -> MCPClient:
    return _GLOBAL_POOL.get_client(endpoint)


def close_all_mcp_clients() -> None:
    _GLOBAL_POOL.close_all()


__all__ = ["MCPClientPool", "close_all_mcp_clients", "get_mcp_client"]
