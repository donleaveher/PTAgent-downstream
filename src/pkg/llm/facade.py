"""
对外推荐入口（保持简单）：

- :func:`build_openai_client` — 与 OpenAI 协议兼容的 HTTP 客户端
- :func:`get_openai_settings_for_ui` — 管理界面展示用（脱敏）
- :func:`test_openai_chat` — 连通性探测
- :func:`get_effective_openai_params` — 解析后的 base / key
"""

from __future__ import annotations

from .openai_runtime import (
    build_openai_client,
    get_effective_openai_params,
    get_openai_settings_for_ui,
    test_openai_chat,
)
from .overrides_store import database_path, load_overrides, overrides_path, save_overrides

__all__ = [
    "build_openai_client",
    "database_path",
    "get_effective_openai_params",
    "get_openai_settings_for_ui",
    "load_overrides",
    "overrides_path",
    "save_overrides",
    "test_openai_chat",
]
