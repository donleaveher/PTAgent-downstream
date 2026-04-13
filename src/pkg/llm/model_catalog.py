"""聊天模型目录：供管理 UI 展示与批量连通性探测（可与 data/llm_models.json 合并）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _data_llm_models_path() -> Path:
    root = Path(__file__).resolve().parents[3]
    d = root / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d / "llm_models.json"


def default_chat_models() -> list[dict[str, Any]]:
    """系统内置的常用 OpenAI 兼容模型 id（可按项目需要改代码或 JSON 覆盖）。"""
    return [
        {"id": "gpt-4o-mini", "label": "GPT-4o mini", "provider": "openai"},
        {"id": "gpt-4o", "label": "GPT-4o", "provider": "openai"},
        {"id": "gpt-4-turbo", "label": "GPT-4 Turbo", "provider": "openai"},
        {"id": "o1-mini", "label": "o1-mini", "provider": "openai"},
        {"id": "o3-mini", "label": "o3-mini", "provider": "openai"},
    ]


def list_chat_models_for_ui() -> list[dict[str, Any]]:
    """返回 ``[{id, label, provider}, ...]``；若存在 ``data/llm_models.json`` 则与其合并（按 id 去重，文件优先）。"""
    base = {m["id"]: dict(m) for m in default_chat_models()}
    p = _data_llm_models_path()
    if p.is_file():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
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
        except (json.JSONDecodeError, OSError):
            pass
    return sorted(base.values(), key=lambda x: x["id"])

