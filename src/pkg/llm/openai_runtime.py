"""OpenAI 兼容 HTTP 客户端构建与有效配置解析（对外简单接口）。"""

from __future__ import annotations

import os
from typing import Any, Optional

from openai import OpenAI

from config import get_settings

from application.mcp_resource_payload import mcp_tools_payload
from application.workflow.llm_workflow import format_mcp_tool_catalog_for_prompt

from .overrides_store import load_overrides


def normalize_openai_base_url(base: Optional[str]) -> Optional[str]:
    """
    OpenAI SDK expects ``base_url`` like ``https://host/v1``, not the full ``.../chat/completions`` path.
    """
    if base is None:
        return None
    b = str(base).strip()
    if not b:
        return None
    b = b.rstrip("/")
    low = b.lower()
    if low.endswith("/chat/completions"):
        b = b[: -len("/chat/completions")].rstrip("/")
    elif low.endswith("/v1/chat/completions"):
        b = b[: -len("/v1/chat/completions")].rstrip("/")
        if not b.lower().endswith("/v1"):
            b = f"{b}/v1"
    return b or None


def normalize_api_key_secret(key: Optional[str]) -> Optional[str]:
    """Strip accidental ``Bearer `` prefix (UI / copy-paste)."""
    if key is None:
        return None
    k = str(key).strip()
    if not k:
        return None
    if k.lower().startswith("bearer "):
        k = k[7:].strip()
    return k or None


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

    优先级：SQLite kv ``llm_overrides`` 中非空字段 > :func:`config.get_settings` > ``OPENAI_API_KEY`` 环境变量。
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
    return normalize_openai_base_url(base), normalize_api_key_secret(key)


def openai_api_configured() -> bool:
    """是否具备可用的 API Key（含 overrides / 环境变量）。"""
    _, key = get_effective_openai_params()
    return bool(key and str(key).strip())


def get_effective_openai_params_for_model(model_id: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
    """
    Resolve base URL + API key for a **specific chat model id** (per-model overrides in
    ``llm_overrides.model_connections``), falling back to global :func:`get_effective_openai_params`.
    """
    base, key = get_effective_openai_params()
    if not model_id or not str(model_id).strip():
        return base, key
    ov = load_overrides()
    raw_mc = ov.get("model_connections")
    if not isinstance(raw_mc, dict):
        return base, key
    mc = raw_mc.get(str(model_id).strip())
    if not isinstance(mc, dict):
        return base, key
    if mc.get("openai_api_base") is not None and str(mc.get("openai_api_base") or "").strip():
        base = normalize_openai_base_url(str(mc["openai_api_base"]).strip())
    if mc.get("openai_api_key") is not None and str(mc.get("openai_api_key") or "").strip():
        key = normalize_api_key_secret(str(mc["openai_api_key"]).strip())
    return base, key


def build_openai_client() -> OpenAI:
    """进程内统一创建 ``OpenAI`` SDK 客户端（Agent / 测试共用；全局连接）。"""
    base, key = get_effective_openai_params()
    kwargs: dict[str, Any] = {}
    if key:
        kwargs["api_key"] = key
    if base:
        kwargs["base_url"] = base
    return OpenAI(**kwargs)


def build_openai_client_for_model(model_id: Optional[str] = None) -> OpenAI:
    """与 :func:`build_openai_client` 相同，但可按模型使用独立 Base/Key。"""
    base, key = get_effective_openai_params_for_model(model_id)
    kwargs: dict[str, Any] = {}
    if key:
        kwargs["api_key"] = key
    if base:
        kwargs["base_url"] = base
    return OpenAI(**kwargs)


def _completion_first_text(resp: Any) -> str:
    ch = getattr(resp, "choices", None)
    if not ch:
        return ""
    first = ch[0]
    msg = getattr(first, "message", None)
    if msg is None:
        return ""
    return (getattr(msg, "content", None) or "").strip()


def get_openai_settings_for_ui(*, include_plaintext_key: bool = False) -> dict[str, Any]:
    """管理界面展示；``include_plaintext_key`` 时返回当前生效的完整密钥（仅管理端使用）。"""
    base, key = get_effective_openai_params()
    m = _mask_key(key)
    out: dict[str, Any] = {
        "openai_api_base": base or "",
        "has_api_key": m["hasKey"],
        "api_key_tail": m["tail"],
        "source_note": "合并顺序：SQLite(llm_overrides) > PTAGENT_OPENAI_* / .env > OPENAI_API_KEY",
        "model_connections": {},
    }
    if include_plaintext_key:
        out["openai_api_key"] = key or ""
    ov = load_overrides()
    raw_mc = ov.get("model_connections")
    if isinstance(raw_mc, dict):
        for mid, row in raw_mc.items():
            if not isinstance(row, dict):
                continue
            mid_s = str(mid).strip()
            if not mid_s:
                continue
            bb = str(row.get("openai_api_base") or "").strip()
            kk = row.get("openai_api_key")
            mk = _mask_key(str(kk).strip() if kk is not None and str(kk).strip() else None)
            ent: dict[str, Any] = {
                "openai_api_base": normalize_openai_base_url(bb) if bb else "",
                "has_api_key": mk["hasKey"],
                "api_key_tail": mk["tail"],
            }
            if include_plaintext_key:
                ent["openai_api_key"] = str(kk).strip() if kk is not None else ""
            out["model_connections"][mid_s] = ent
    return out


def _merge_system_with_mcp_catalog(system: str | None, *, include_mcp_catalog: bool) -> str | None:
    if not include_mcp_catalog:
        return str(system).strip() if system and str(system).strip() else None
    payload = mcp_tools_payload()
    tools = payload.get("tools") or []
    block = format_mcp_tool_catalog_for_prompt(tools)
    extra = (
        "## Registered MCP tools (use EXACT `tool` names in workflow JSON when applicable)\n"
        + block
        + "\n\n## Required output format\n"
        + "After concise reasoning, output ONE fenced block ```workflow with valid JSON only, for example:\n"
        "```workflow\n"
        '{"steps":[{"id":"1","title":"Step title","tool":"exact_mcp_tool_name_or_null","description":"What to run"}],"notes":""}\n'
        "```\n"
        + "Use JSON `null` for `tool` when the step is manual or not an MCP call. Keys stay in English: "
        "`steps`, `id`, `title`, `tool`, `description`, `notes`."
    )
    if system and str(system).strip():
        return str(system).strip() + "\n\n" + extra
    return extra


def _messages_for_chat(
    *,
    messages: list[dict[str, str]],
    system: str | None,
    include_mcp_catalog: bool,
) -> list[dict[str, str]]:
    merged = _merge_system_with_mcp_catalog(system, include_mcp_catalog=include_mcp_catalog)
    msgs: list[dict[str, str]] = []
    if merged:
        msgs.append({"role": "system", "content": merged})
    for m in messages:
        role = str(m.get("role") or "user").strip()
        content = str(m.get("content") or "")
        if role not in ("system", "user", "assistant"):
            role = "user"
        msgs.append({"role": role, "content": content})
    return msgs


def chat_completion_messages(
    *,
    model: str = "gpt-4o-mini",
    messages: list[dict[str, str]],
    system: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    include_mcp_catalog: bool = True,
) -> dict[str, Any]:
    """Multi-turn chat for workflow planning UI (OpenAI-compatible messages)."""
    msgs = _messages_for_chat(
        messages=messages, system=system, include_mcp_catalog=include_mcp_catalog
    )
    try:
        client = build_openai_client_for_model(model)
        resp = client.chat.completions.create(
            model=model,
            messages=msgs,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = _completion_first_text(resp)
        if not text and not getattr(resp, "choices", None):
            return {
                "ok": False,
                "model": model,
                "error": "empty choices in API response",
            }
        return {"ok": True, "model": model, "reply": text}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "model": model, "error": str(exc)}


def _delta_content_to_text(delta: Any) -> str:
    """Normalize streaming ``delta.content`` (str, list of parts, or SDK objects) to text."""
    if delta is None:
        return ""
    raw = getattr(delta, "content", None)
    if raw is None:
        # Some gateways expose reasoning separately (ignore if not plain text)
        rc = getattr(delta, "reasoning_content", None)
        if isinstance(rc, str) and rc.strip():
            return rc
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                t = item.get("text")
                if isinstance(t, str):
                    parts.append(t)
                elif item.get("type") == "text" and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return str(raw)


def iter_chat_completion_messages_stream(
    *,
    model: str = "gpt-4o-mini",
    messages: list[dict[str, str]],
    system: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.3,
    include_mcp_catalog: bool = True,
):
    """Yield text deltas from OpenAI streaming chat completions."""
    msgs = _messages_for_chat(
        messages=messages, system=system, include_mcp_catalog=include_mcp_catalog
    )
    client = build_openai_client_for_model(model)
    stream = client.chat.completions.create(
        model=model,
        messages=msgs,
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True,
    )
    for chunk in stream:
        ch = getattr(chunk, "choices", None)
        if not ch:
            continue
        choice = ch[0]
        delta = getattr(choice, "delta", None)
        if delta is None:
            continue
        piece = _delta_content_to_text(delta)
        if piece:
            yield piece


def test_openai_chat(*, model: str = "gpt-4o-mini", user_message: str = "ping") -> dict[str, Any]:
    """发起一次最小 chat 调用，用于连通性检测。"""
    client = build_openai_client_for_model(model)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=16,
            temperature=0,
        )
        if not getattr(resp, "choices", None):
            return {
                "ok": False,
                "model": model,
                "error": "empty choices in API response (check API Base is …/v1 not …/chat/completions; key without 'Bearer ' prefix)",
            }
        text = _completion_first_text(resp)
        return {"ok": True, "model": model, "reply_preview": text[:500]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "model": model, "error": str(exc)}


