from __future__ import annotations

from typing import Any, Mapping, Optional

import requests

from config import get_settings

from .base import LLMClient


class GLMLLMClient(LLMClient):
    """
    GLM / 智谱 的简单 HTTP 客户端实现。

    - 使用 settings.glm_api_base / settings.glm_api_key
    - 假定提供兼容 Chat Completions 风格的 HTTP 接口（需按你的实际 GLM 接口调整）
    """

    def __init__(self, *, api_key: Optional[str] = None, api_base: Optional[str] = None) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.glm_api_key
        self._api_base = (api_base or settings.glm_api_base or "").rstrip("/")

    def generate(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        temperature: float = 0.7,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> str:
        if not self._api_base or not self._api_key:
            raise RuntimeError("GLM API base 或 API key 未配置。")

        # 这里构造一个通用的 Chat Completions 风格请求体，具体字段可根据实际 GLM 接口调整
        url = f"{self._api_base}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
        }
        payload: dict[str, Any] = {
            "model": model or "glm-5",
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
        }
        if extra:
            payload.update(extra)

        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        # 兼容 OpenAI 风格响应：data["choices"][0]["message"]["content"]
        try:
            return data["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"GLM 响应解析失败: {data}") from exc

