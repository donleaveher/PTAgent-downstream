from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping, Optional


class LLMClient(ABC):
    """
    LLM 抽象基类。

    企业级设计要求：
    - 不直接依赖具体 Provider（OpenAI、本地模型等）；
    - 统一暴露最小必要接口（例如 generate），方便在多 Agent / RAG 中调用；
    - 具体 Provider 的实现放在独立模块中（如 openai_client.py）。
    """

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        temperature: float = 0.1,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> str:
        """同步生成一个文本回复。"""

