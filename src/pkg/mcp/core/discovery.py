from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from time import time
from typing import Any, Dict, List, Optional


@dataclass
class MCPService:
    """A discoverable MCP service instance."""

    service_id: str
    name: str
    endpoint: str
    protocol: str = "websocket"
    metadata: Dict[str, Any] = field(default_factory=dict)
    registered_at: float = field(default_factory=time)
    last_heartbeat_at: float = field(default_factory=time)


class MCPDiscoveryCenter:
    """In-memory discovery center for MCP services."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._services: Dict[str, MCPService] = {}

    def register_service(self, service: MCPService) -> None:
        with self._lock:
            self._services[service.service_id] = service

    def unregister_service(self, service_id: str) -> None:
        with self._lock:
            self._services.pop(service_id, None)

    def heartbeat(self, service_id: str) -> None:
        with self._lock:
            svc = self._services.get(service_id)
            if svc is None:
                return
            svc.last_heartbeat_at = time()

    def get_service(self, service_id: str) -> Optional[MCPService]:
        with self._lock:
            return self._services.get(service_id)

    def list_services(self) -> List[MCPService]:
        with self._lock:
            return list(self._services.values())

    def discover_endpoint(self, *, service_name: Optional[str] = None) -> Optional[str]:
        with self._lock:
            services = list(self._services.values())
        if not services:
            return None
        if service_name:
            for svc in services:
                if svc.name == service_name:
                    return svc.endpoint
            return None
        return services[0].endpoint


_CENTER = MCPDiscoveryCenter()


def register_service(service: MCPService) -> None:
    _CENTER.register_service(service)


def unregister_service(service_id: str) -> None:
    _CENTER.unregister_service(service_id)


def heartbeat(service_id: str) -> None:
    _CENTER.heartbeat(service_id)


def get_service(service_id: str) -> Optional[MCPService]:
    return _CENTER.get_service(service_id)


def list_services() -> List[MCPService]:
    return _CENTER.list_services()


def discover_endpoint(*, service_name: Optional[str] = None) -> Optional[str]:
    return _CENTER.discover_endpoint(service_name=service_name)


__all__ = [
    "MCPService",
    "MCPDiscoveryCenter",
    "register_service",
    "unregister_service",
    "heartbeat",
    "get_service",
    "list_services",
    "discover_endpoint",
]
