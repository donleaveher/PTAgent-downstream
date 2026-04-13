"""
已注册的 MCP 工具 Provider 子进程入口（键 → ``模块:可调用对象``）。

新增子项目时：在此增加 ``PROVIDER_SCRIPTS`` 项，并在 Provider 内用 ``@tool(..., category=..., group=...)`` 声明
Admin 分组（随 ``provider/register`` 写入 Broker / MCP Tool meta，无需单独 catalog 文件）。
"""

from __future__ import annotations

# 键为简短 ID，供环境变量 MCP_TOOLS_PROVIDERS 使用
PROVIDER_SCRIPTS: dict[str, str] = {
    "basic.peptide": "mcp_tools.basic.peptide.provider:run_blocking",
}

DEFAULT_PROVIDERS = "basic.peptide"
