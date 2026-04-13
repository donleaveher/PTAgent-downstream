"""示例：继承 ToolProvider，注册加法工具。"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
load_dotenv(dotenv_path=Path(__file__).resolve().parents[3] / ".env")

from config import get_mcp_settings
from pkg.mcp import ToolProvider, tool


class MathTools(ToolProvider):
    provider_label = "demo-math-provider"

    @tool(description="Add two numbers.")
    def add(self, a: float, b: float) -> dict:
        return {"a": a, "b": b, "sum": a + b}


if __name__ == "__main__":
    MathTools(get_mcp_settings().endpoint).run()
