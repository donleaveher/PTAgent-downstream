"""
application 包：产品策略、持久化与用例编排（与 ``pkg`` 内核分离）。

- ``application.agent``：Agent/Team SQLite、kv（``store`` / ``records``）
- ``application.workflow``：LLM 提示词侧工具目录等（如 ``llm_workflow``）
- ``application.command``：通用命令占位
- ``application.ptagent_admin``：Admin / 向导等业务用例
- ``application.mcp_resource_payload`` / ``application.mcp_tool_arg_presets``：MCP 控制台相关产品逻辑
"""

from __future__ import annotations

__all__: list[str] = []
