"""
宿主应用提供的 MCP 字段约定文档加载器。

- **默认**尝试导入 ``config.mcp_conventions`` 并读取 ``CONVENTIONS_DOCUMENT``。
- 可通过环境变量 ``PTAGENT_MCP_CONVENTIONS_MODULE`` 指向其它模块（需导出同名常量）。

``pkg.mcp`` 本身不包含业务字段表；仅提供上述接入方式，供 Admin ``/api/conventions`` 使用。
"""

from __future__ import annotations

import importlib
import os
from typing import Any

_DEFAULT_MODULE = "config.mcp_conventions"
_ENV_KEY = "PTAGENT_MCP_CONVENTIONS_MODULE"


def load_conventions_document() -> dict[str, Any]:
    """
    加载 MCP 字段约定 JSON 文档（dict）。

    导入失败时返回占位内容，避免 Admin 报错；此时应检查 ``PYTHONPATH`` 是否包含 ``src``
    或是否正确设置 ``PTAGENT_MCP_CONVENTIONS_MODULE``。
    """
    name = os.environ.get(_ENV_KEY, "").strip() or _DEFAULT_MODULE
    try:
        m = importlib.import_module(name)
        doc = getattr(m, "CONVENTIONS_DOCUMENT", None)
        if isinstance(doc, dict):
            return dict(doc)
    except Exception:  # noqa: BLE001
        pass
    return {
        "version": 0,
        "title": "MCP 字段约定（未加载）",
        "rules": [
            f"未能导入约定模块 {name!r}。请保证 PYTHONPATH 含 src，且存在 config.mcp_conventions，"
            f"或设置 {_ENV_KEY} 指向导出 CONVENTIONS_DOCUMENT 的模块。",
        ],
        "fields": [],
    }


__all__ = ["load_conventions_document"]
