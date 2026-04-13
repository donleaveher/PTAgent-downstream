from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from pkg.mcp.mcp_framework import MCPBroker
from pkg.mcp.mcp_framework.config import BrokerConfig
from pkg.mcp.mcp_framework.endpoints import resolve_listen_address, split_mcp_endpoints


class MCPService:
    """
    在本进程内承载 MCP Broker（FastMCP HTTP + Provider WebSocket）。

    - ``asgi_app()``：交给 uvicorn / gunicorn 等加载；
    - ``run()``：本地阻塞调试；
    - ``ensure_subprocess``：由主进程拉起独立 Python 子进程跑 Broker。
    """

    def __init__(self, config: BrokerConfig | None = None) -> None:
        self._broker = MCPBroker(config)

    def asgi_app(self) -> Any:
        return self._broker.asgi_app()

    def run(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
        *,
        log_level: str = "info",
    ) -> None:
        self._broker.run(host=host, port=port, log_level=log_level)

    @staticmethod
    def ensure_subprocess(
        *,
        endpoint: str | None,
        project_root: str,
        pid_file: str = "/tmp/ptagent-mcp-server.pid",
        wait_ready_timeout_seconds: float = 8.0,
    ) -> bool:
        if not endpoint:
            return False
        http_url, _ = split_mcp_endpoints(endpoint)
        if not http_url:
            return False

        pid_path = Path(pid_file)
        if pid_path.exists():
            try:
                old_pid = int(pid_path.read_text(encoding="utf-8").strip())
                if _is_process_alive(old_pid) and _is_expected_mcp_process(old_pid):
                    return False
            except ValueError:
                pass

        host, port = resolve_listen_address(http_url)
        code = (
            "from pkg.mcp.mcp_framework import MCPBroker; "
            f"MCPBroker().run(host={host!r}, port={port})"
        )
        env = os.environ.copy()
        src_root = Path(project_root).resolve() / "src"
        if src_root.is_dir():
            env["PYTHONPATH"] = str(src_root) + os.pathsep + env.get("PYTHONPATH", "")

        process = subprocess.Popen(  # noqa: S603
            [sys.executable, "-c", code],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        pid_path.write_text(str(process.pid), encoding="utf-8")

        deadline = time.time() + wait_ready_timeout_seconds
        while time.time() < deadline:
            if process.poll() is not None:
                break
            try:
                with socket.create_connection((host, port), timeout=0.3):
                    break
            except OSError:
                time.sleep(0.1)
        return True


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _is_expected_mcp_process(pid: int) -> bool:
    cmdline_path = Path(f"/proc/{pid}/cmdline")
    try:
        data = cmdline_path.read_bytes()
    except OSError:
        return False
    if not data:
        return False
    joined = data.decode("utf-8", errors="ignore").replace("\x00", " ")
    return "pkg.mcp.mcp_framework" in joined and "MCPBroker" in joined


__all__ = ["MCPService"]
