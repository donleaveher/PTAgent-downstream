from __future__ import annotations

from typing import Any, Optional

import anyio
import uvicorn
from fastmcp import FastMCP

from .broker import ToolBroker, build_broker_asgi_app
from .config import BrokerConfig
from .discovery import MCPService, register_service, unregister_service
from .endpoints import http_base_from_mcp_url


class MCPBroker:
    """
    对外主入口：封装「FastMCP HTTP + Provider WebSocket」组合 ASGI 应用。

    典型用法::

        broker = MCPBroker()
        app = broker.asgi_app()
        # 交给 uvicorn / gunicorn / hypercorn 加载 app

    或开发时直接阻塞运行::

        MCPBroker().run(host="127.0.0.1", port=8765)
    """

    def __init__(self, config: Optional[BrokerConfig] = None) -> None:
        self._config = config or BrokerConfig()
        self._engine = ToolBroker(self._config)

    @property
    def config(self) -> BrokerConfig:
        return self._config

    @property
    def engine(self) -> ToolBroker:
        """底层注册表与中继（进阶用法）。"""
        return self._engine

    @property
    def fast_mcp(self) -> FastMCP:
        """底层 FastMCP 实例。"""
        return self._engine.mcp

    def asgi_app(self) -> Any:
        """返回可挂载的 ASGI 应用（Starlette）。"""
        return build_broker_asgi_app(self._engine)

    def run(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        *,
        log_level: str = "info",
    ) -> None:
        """
        使用内置 uvicorn 阻塞运行（便于本地调试；生产建议只取 ``asgi_app()``）。
        """
        sid = self._config.discovery_service_id
        http_mcp_url = f"http://{host}:{port}{self._config.mcp_http_path}"
        if host in {"0.0.0.0", "::"}:
            http_mcp_url = f"http://127.0.0.1:{port}{self._config.mcp_http_path}"

        if sid:
            meta = {
                "runtime": "pkg.mcp.core",
                "mcpPath": self._config.mcp_http_path,
                "providerPath": self._config.provider_ws_path,
                **self._config.discovery_metadata,
            }
            register_service(
                MCPService(
                    service_id=sid,
                    name=self._config.discovery_service_name,
                    endpoint=http_base_from_mcp_url(http_mcp_url),
                    protocol=self._config.discovery_protocol,
                    metadata=meta,
                )
            )

        app = self.asgi_app()

        async def _serve() -> None:
            config = uvicorn.Config(
                app,
                host=host,
                port=port,
                timeout_graceful_shutdown=2,
                lifespan="on",
                ws="websockets-sansio",
                log_level=log_level.lower(),
            )
            await uvicorn.Server(config).serve()

        try:
            anyio.run(_serve)
        finally:
            if sid:
                unregister_service(sid)
