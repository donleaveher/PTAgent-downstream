"""聊天模型目录：供管理 UI 展示与批量连通性探测（与 SQLite kv ``llm_models`` 合并）。"""

from __future__ import annotations

import json
from typing import Any


def default_chat_models() -> list[dict[str, Any]]:
    """系统内置的常用 OpenAI 兼容模型 id。"""
    return [
        {"id": "gpt-4o-mini", "label": "GPT-4o mini", "provider": "openai"},
        {"id": "gpt-4o", "label": "GPT-4o", "provider": "openai"},
        {"id": "gpt-4-turbo", "label": "GPT-4 Turbo", "provider": "openai"},
        {"id": "o1-mini", "label": "o1-mini", "provider": "openai"},
        {"id": "o3-mini", "label": "o3-mini", "provider": "openai"},
    ]


def list_chat_models_for_ui() -> list[dict[str, Any]]:
    """返回 ``[{id, label, provider}, ...]``；与 kv ``llm_models`` 合并（按 id 去重，kv 优先）。"""
    from config.database_settings import resolve_database_path
    from application.agent.store import kv_get

    base = {m["id"]: dict(m) for m in default_chat_models()}
    raw_s = kv_get(resolve_database_path(), "llm_models")
    if raw_s:
        try:
            raw = json.loads(raw_s)
            arr = raw.get("models") if isinstance(raw, dict) else raw
            if isinstance(arr, list):
                for item in arr:
                    if not isinstance(item, dict):
                        continue
                    mid = str(item.get("id") or "").strip()
                    if not mid:
                        continue
                    base[mid] = {
                        "id": mid,
                        "label": str(item.get("label") or mid),
                        "provider": str(item.get("provider") or "custom"),
                    }
        except json.JSONDecodeError:
            pass
    return sorted(base.values(), key=lambda x: x["id"])
