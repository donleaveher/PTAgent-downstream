"""前端目录绝对路径（供 FastAPI 路由挂载 FileResponse）。"""

from __future__ import annotations

from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parent
SHARED = FRONTEND_DIR / "shared"
PTAGENT = FRONTEND_DIR / "ptagent"
MCP = FRONTEND_DIR / "mcp"
AGENT_STUDIO = FRONTEND_DIR / "agent_studio"
