"""OpenAI 兼容端点覆盖（存于统一 SQLite 的 kv，键 ``llm_overrides``，优先于环境变量中的 PTAGENT_ 配置）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def database_path() -> Path:
    """当前使用的 SQLite 文件路径（与 Agent/Team 同库）。"""
    from config.database_settings import resolve_database_path

    return resolve_database_path()


def overrides_path() -> Path:
    """兼容旧名：与 :func:`database_path` 相同。"""
    return database_path()


def load_overrides() -> dict[str, Any]:
    from application.agent.store import kv_get

    raw = kv_get(database_path(), "llm_overrides")
    if not raw:
        return {}
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else {}
    except json.JSONDecodeError:
        return {}


def save_overrides(data: dict[str, Any]) -> None:
    from application.agent.store import kv_set

    kv_set(database_path(), "llm_overrides", json.dumps(data, ensure_ascii=False))
