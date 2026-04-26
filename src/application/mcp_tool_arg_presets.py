"""MCP 控制台「示例参数」：读写 SQLite ``kv.mcp_tool_arg_presets``（产品数据，非通用库）。"""

from __future__ import annotations

import json
from typing import Any

_KV_KEY = "mcp_tool_arg_presets"


def _load_stored_raw() -> dict[str, dict[str, Any]]:
    from config.database_settings import resolve_database_path
    from application.agent.store import kv_get

    raw = kv_get(resolve_database_path(), _KV_KEY)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for k, v in data.items():
        if isinstance(v, dict):
            out[str(k)] = dict(v)
    return out


def merge_tool_arg_presets() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    p = _load_stored_raw()
    return p, p


def replace_stored_tool_arg_presets(stored: dict[str, dict[str, Any]]) -> None:
    from config.database_settings import resolve_database_path
    from application.agent.store import kv_set

    clean: dict[str, dict[str, Any]] = {}
    for k, v in stored.items():
        if isinstance(v, dict):
            clean[str(k)] = dict(v)
    kv_set(resolve_database_path(), _KV_KEY, json.dumps(clean, ensure_ascii=False))


def upsert_stored_tool_arg_preset(tool_name: str, arguments: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cur = _load_stored_raw()
    cur[tool_name] = dict(arguments)
    replace_stored_tool_arg_presets(cur)
    return cur


__all__ = [
    "merge_tool_arg_presets",
    "replace_stored_tool_arg_presets",
    "upsert_stored_tool_arg_preset",
]
