from __future__ import annotations

from typing import Any, Mapping, Optional

from openai import OpenAI

from config import get_settings

from .base import LLMClient


class OpenAILLMClient(LLMClient):
    """
    OpenAI Provider 的具体实现。

    - URL 和密钥均从 AppSettings 中读取：
      - settings.openai_api_base
      - settings.openai_api_key
    - 若未在配置中提供 api_key，则退回使用环境变量 OPENAI_API_KEY。
    """

    def __init__(self, *, api_key: Optional[str] = None, api_base: Optional[str] = None) -> None:
        settings = get_settings()
        key = api_key or settings.openai_api_key
        base_url = api_base or settings.openai_api_base

        client_kwargs: dict[str, Any] = {}
        if key is not None:
            client_kwargs["api_key"] = key
        if base_url is not None:
            client_kwargs["base_url"] = base_url

        self._client = OpenAI(**client_kwargs)

    def generate(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        temperature: float = 0.1,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> str:
        model_name = model or "gpt-4o-mini"
        params: dict[str, Any] = {"temperature": temperature}
        if extra:
            params.update(extra)

        resp = self._client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            **params,
        )
        return resp.choices[0].message.content or ""

