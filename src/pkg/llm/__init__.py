"""
LLM 子包：多 Provider 注册表 + OpenAI 兼容运行时（进程内统一客户端与 UI 用配置）。

推荐对外使用：
- :func:`build_openai_client`、:func:`get_openai_settings_for_ui`、:func:`test_openai_chat`（见 ``facade``）
- 或 ``from pkg.llm import build_openai_client`` 等稳定别名
- 历史抽象：``LLMClient`` / ``ModelRegistry``（可选）
"""

from .base import LLMClient
from .facade import (
    build_openai_client,
    get_effective_openai_params,
    get_openai_settings_for_ui,
    load_overrides,
    overrides_path,
    save_overrides,
    test_openai_chat,
)
from .model_catalog import list_chat_models_for_ui
from .registry import ModelProvider, ModelRegistry, ModelSpec

__all__ = [
    "LLMClient",
    "ModelProvider",
    "ModelSpec",
    "ModelRegistry",
    "build_openai_client",
    "get_effective_openai_params",
    "get_openai_settings_for_ui",
    "load_overrides",
    "overrides_path",
    "save_overrides",
    "test_openai_chat",
    "list_chat_models_for_ui",
]

