"""OpenAI 兼容 HTTP 客户端构建与有效配置解析（对外简单接口）。"""

from __future__ import annotations

import os
from typing import Any, Optional

from openai import OpenAI

from config import get_settings

from .overrides_store import load_overrides


def _mask_key(key: Optional[str]) -> dict[str, Any]:
    if not key:
        return {"hasKey": False, "tail": None}
    k = str(key).strip()
    if len(k) <= 8:
        return {"hasKey": True, "tail": "****"}
    return {"hasKey": True, "tail": "…" + k[-4:]}


def get_effective_openai_params() -> tuple[Optional[str], Optional[str]]:
    """
    返回 ``(api_base, api_key)`` 供 ``OpenAI`` 客户端使用。

    优先级：``llm_overrides.json`` 非空字段 > :func:`config.get_settings` > ``OPENAI_API_KEY`` 环境变量。
    """
    s = get_settings()
    base = s.openai_api_base
    key = s.openai_api_key or os.environ.get("OPENAI_API_KEY")
    ov = load_overrides()
    if ov.get("openai_api_base") is not None:
        b = ov.get("openai_api_base")
        base = str(b).strip() if b else None
    if "openai_api_key" in ov:
        ok = ov.get("openai_api_key")
        if ok is None or (isinstance(ok, str) and not ok.strip()):
            key = s.openai_api_key or os.environ.get("OPENAI_API_KEY")
        else:
            key = str(ok).strip()
    return base, key


def openai_api_configured() -> bool:
    """是否具备可用的 API Key（含 overrides / 环境变量）。"""
    _, key = get_effective_openai_params()
    return bool(key and str(key).strip())


def build_openai_client() -> OpenAI:
    """进程内统一创建 ``OpenAI`` SDK 客户端（Agent / 测试共用）。"""
    base, key = get_effective_openai_params()
    kwargs: dict[str, Any] = {}
    if key:
        kwargs["api_key"] = key
    if base:
        kwargs["base_url"] = base
    return OpenAI(**kwargs)


def get_openai_settings_for_ui(*, include_plaintext_key: bool = False) -> dict[str, Any]:
    """管理界面展示；``include_plaintext_key`` 时返回当前生效的完整密钥（仅管理端使用）。"""
    base, key = get_effective_openai_params()
    m = _mask_key(key)
    out: dict[str, Any] = {
        "openai_api_base": base or "",
        "has_api_key": m["hasKey"],
        "api_key_tail": m["tail"],
        "source_note": "合并顺序：data/llm_overrides.json > PTAGENT_OPENAI_* / .env > OPENAI_API_KEY",
    }
    if include_plaintext_key:
        out["openai_api_key"] = key or ""
    return out


def test_openai_chat(*, model: str = "gpt-4o-mini", user_message: str = "ping") -> dict[str, Any]:
    """发起一次最小 chat 调用，用于连通性检测。"""
    client = build_openai_client()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=16,
            temperature=0,
        )
        text = (resp.choices[0].message.content or "").strip()
        return {"ok": True, "model": model, "reply_preview": text[:500]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "model": model, "error": str(exc)}
