"""示例：继承 ToolProvider，向 Broker 注册 ping 工具（需先启动 MCPService）。"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
load_dotenv(dotenv_path=Path(__file__).resolve().parents[3] / ".env")

from config import get_mcp_settings
from pkg.mcp import ToolProvider, tool


class PingTools(ToolProvider):
    provider_label = "demo-ws-provider"

    @tool(description="Ping tool provided by demo provider.")
    def ping(self) -> dict:
        return {"status": "ok"}


if __name__ == "__main__":
    PingTools(get_mcp_settings().endpoint).run()
