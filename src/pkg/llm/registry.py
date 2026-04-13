from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Mapping, Optional

from config import AppSettings, get_settings

from .base import LLMClient
from .glm_client import GLMLLMClient
from .openai_compatible import OpenAICompatibleClient


class ModelProvider(str, Enum):
    """模型提供方类型。"""

    OPENAI = "openai"
    QWEN = "qwen"
    DEEPSEEK = "deepseek"
    HKUST_GPT = "hkust_gpt"
    GLM = "glm"
    # 预留：企业内部 / 本地模型 Provider
    LOCAL = "local"


@dataclass
class ModelSpec:
    """
    单个模型的规格描述。

    - name：逻辑名（如 proteomics_explainer）
    - provider：提供方（OPENAI/LOCAL/…）
    - model：底层模型 ID（如 gpt-4o、自研模型名等）
    """

    name: str
    provider: ModelProvider
    model: str


class ModelRegistry:
    """
    模型注册表：统一管理“若干模型”。

    企业级设计特点：
    - 与 Provider 解耦：只保存 ModelSpec，不直接持有 SDK 对象；
    - 按需惰性创建 LLMClient（OpenAI、本地等），并做缓存；
    - 支持通过配置/代码扩展更多逻辑模型。
    """

    def __init__(self, settings: Optional[AppSettings] = None) -> None:
        self._settings = settings or get_settings()
        self._models: Dict[str, ModelSpec] = {}
        self._clients: Dict[ModelProvider, LLMClient] = {}

        # 默认注册一个通用模型（可在初始化时或运行中覆写）
        self.register_model(
            "default",
            ModelSpec(name="default", provider=ModelProvider.OPENAI, model="gpt-4o-mini"),
        )

    def register_model(self, logical_name: str, spec: ModelSpec) -> None:
        self._models[logical_name] = spec

    def get_model_spec(self, logical_name: str) -> ModelSpec:
        if logical_name not in self._models:
            raise KeyError(f"Unknown model logical name: {logical_name}")
        return self._models[logical_name]

    def _get_client(self, provider: ModelProvider) -> LLMClient:
        if provider in self._clients:
            return self._clients[provider]

        if provider is ModelProvider.OPENAI:
            client = OpenAICompatibleClient(
                api_key=self._settings.openai_api_key,
                api_base=self._settings.openai_api_base,
                default_model="gpt-4o-mini",
                default_temperature=0.3,
            )
        elif provider is ModelProvider.QWEN:
            client = OpenAICompatibleClient(
                api_key=self._settings.qwen_api_key,
                api_base=self._settings.qwen_api_base,
                default_model="qwen3-max",
                default_temperature=0.1,
            )
        elif provider is ModelProvider.DEEPSEEK:
            client = OpenAICompatibleClient(
                api_key=self._settings.deepseek_api_key,
                api_base=self._settings.deepseek_api_base,
                default_model="deepseek-chat",
                default_temperature=0.3,
            )
        elif provider is ModelProvider.HKUST_GPT:
            client = OpenAICompatibleClient(
                api_key=self._settings.hkust_gpt_api_key,
                api_base=self._settings.hkust_gpt_api_base,
                default_model="gpt-4o",
                default_temperature=0.5,
            )
        elif provider is ModelProvider.GLM:
            client = GLMLLMClient()
        else:
            # 后续可在此扩展 LOCAL 等 Provider 的实现
            raise NotImplementedError(f"Model provider {provider} not implemented yet.")

        self._clients[provider] = client
        return client

    def generate(
        self,
        logical_name: str,
        prompt: str,
        *,
        temperature: float = 0.1,
        extra: Optional[Mapping[str, object]] = None,
    ) -> str:
        spec = self.get_model_spec(logical_name)
        client = self._get_client(spec.provider)
        return client.generate(prompt, model=spec.model, temperature=temperature, extra=extra)

