from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Dict

from pkg.mcp.client_pool import MCPClientPool


@dataclass
class GlobalObjects:
    """
    Process-wide shared objects container.

    Add more shared resources here later, e.g.:
    - db_engine
    - redis_client
    - model_runtime
    """

    mcp_client_pool: MCPClientPool = field(default_factory=MCPClientPool)
    extras: Dict[str, Any] = field(default_factory=dict)

    def close(self) -> None:
        self.mcp_client_pool.close_all()


_LOCK = Lock()
_GLOBAL: GlobalObjects | None = None


def get_global_objects() -> GlobalObjects:
    global _GLOBAL
    with _LOCK:
        if _GLOBAL is None:
            _GLOBAL = GlobalObjects()
        return _GLOBAL


def close_global_objects() -> None:
    global _GLOBAL
    with _LOCK:
        obj = _GLOBAL
        _GLOBAL = None
    if obj is not None:
        obj.close()


__all__ = ["GlobalObjects", "get_global_objects", "close_global_objects"]
