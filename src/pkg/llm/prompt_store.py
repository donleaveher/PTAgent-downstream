"""LLM 前端用 System Prompt 存 SQLite kv（键 ``llm_prompts``），管理端可编辑。"""

from __future__ import annotations

import json
from typing import Any

from application.agent.store import kv_get, kv_set
from pkg.llm.overrides_store import database_path

KV_KEY = "llm_prompts"

# 与路由 / 前端约定的键名
PROMPT_KEYS = frozenset({"guided_experiment", "spectrum_chat", "workflow_extra_instructions"})

DEFAULT_PROMPTS: dict[str, str] = {
    "guided_experiment": (
        "You are a senior mass spectrometry / proteomics method planner.\n"
        "The user message includes full experiment context (instrument, species, file paths, background).\n"
        "Respond in English: brief reasoning, then ONE ```workflow fenced block with valid JSON only, "
        "as required in the server system message (steps may reference registered MCP tools by exact `tool` name, or null).\n"
        "Planning only — do not claim tools were executed or that you saw real run logs."
    ),
    "spectrum_chat": (
        "You are a mass spectrometry assistant for quick spectrum-level exploration.\n"
        "The user message may include an MGF excerpt and/or a single-spectrum JSON (peaks, precursor m/z, charge) and an optional server file path.\n"
        "Respond in English with concise reasoning, then ONE ```workflow JSON block per server format.\n"
        "Planning only — do not claim external tools were executed."
    ),
    "workflow_extra_instructions": "",
}


def _parse_stored(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(d, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in d.items():
        ks = str(k).strip()
        if ks in PROMPT_KEYS and isinstance(v, str):
            out[ks] = v
    return out


def load_prompts() -> dict[str, str]:
    """合并默认值与数据库覆盖。"""
    raw = kv_get(database_path(), KV_KEY)
    stored = _parse_stored(raw)
    merged = dict(DEFAULT_PROMPTS)
    merged.update(stored)
    return merged


def save_prompts(updates: dict[str, Any]) -> dict[str, str]:
    """写入若干键；返回合并后的全量。"""
    cur = load_prompts()
    for k, v in updates.items():
        ks = str(k).strip()
        if ks in PROMPT_KEYS and isinstance(v, str):
            cur[ks] = v
    kv_set(database_path(), KV_KEY, json.dumps(cur, ensure_ascii=False))
    return cur


def build_system_for_chat(
    *,
    prompt_key: str,
    system_override: str | None = None,
) -> str | None:
    """
    解析最终传入 OpenAI 的 system 文本（不含 MCP 列表；由 openai_runtime 再合并）。

    - 若 ``system_override`` 非空，直接使用（管理端 / 调试）。
    - 否则使用 ``prompt_key`` 对应库存文案 + 可选 ``workflow_extra_instructions``。
    """
    if system_override is not None and str(system_override).strip():
        return str(system_override).strip()
    prompts = load_prompts()
    pk = str(prompt_key or "guided_experiment").strip()
    if pk not in ("guided_experiment", "spectrum_chat"):
        pk = "guided_experiment"
    base = (prompts.get(pk) or DEFAULT_PROMPTS.get(pk) or "").strip()
    extra = (prompts.get("workflow_extra_instructions") or "").strip()
    parts = [p for p in (base, extra) if p]
    if not parts:
        return None
    return "\n\n".join(parts)


__all__ = [
    "DEFAULT_PROMPTS",
    "KV_KEY",
    "PROMPT_KEYS",
    "build_system_for_chat",
    "load_prompts",
    "save_prompts",
]
