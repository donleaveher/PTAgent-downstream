from __future__ import annotations

from typing import Any, Mapping, Optional

from openai import OpenAI

from .base import LLMClient


class OpenAICompatibleClient(LLMClient):
    """
    统一的 OpenAI 协议兼容客户端。

    用于所有“Chat Completions 兼容”的服务（OpenAI、Qwen、DeepSeek、HKUST GPT 等），
    由调用方传入 base_url 和 api_key，避免为每个 Provider 写重复代码。
    """

    def __init__(
        self,
        *,
        api_key: Optional[str],
        api_base: Optional[str],
        default_model: str,
        default_temperature: float = 0.3,
    ) -> None:
        self._default_model = default_model
        self._default_temperature = default_temperature

        client_kwargs: dict[str, Any] = {}
        if api_key is not None:
            client_kwargs["api_key"] = api_key
        if api_base is not None:
            client_kwargs["base_url"] = api_base

        self._client = OpenAI(**client_kwargs)

    def generate(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        temperature: float = 0.1,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> str:
        model_name = model or self._default_model
        temp = temperature if temperature is not None else self._default_temperature

        params: dict[str, Any] = {"temperature": temp}
        if extra:
            params.update(extra)

        resp = self._client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            **params,
        )
        return resp.choices[0].message.content or ""

