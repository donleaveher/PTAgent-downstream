"""
产品侧 Agent / Team 持久化与记录模型。

- ``records`` — ``TeamSpec``、与 ``AgentSpec`` 之间的 dict 映射
- ``store`` — SQLite、``kv_get`` / ``kv_set``、:class:`SqliteAgentRegistryStore`

执行图编译与 LangGraph 仍使用 ``pkg.agent``。
"""

from __future__ import annotations

from config.database_settings import resolve_database_path

from pkg.agent.team_spec import TeamSpec

from .records import (
    agent_spec_to_record,
    record_to_agent_spec,
    record_to_team,
    team_to_record,
)
from .store import SqliteAgentRegistryStore, ensure_database_schema, kv_get, kv_set

_STORE: SqliteAgentRegistryStore | None = None


def get_registry_store() -> SqliteAgentRegistryStore:
    """
    进程内单例：统一 SQLite（默认 ``data/ptagent.db``）。

    首次访问时打开或创建库文件。
    """
    global _STORE
    if _STORE is None:
        _STORE = SqliteAgentRegistryStore(resolve_database_path())
    return _STORE


__all__ = [
    "SqliteAgentRegistryStore",
    "TeamSpec",
    "agent_spec_to_record",
    "ensure_database_schema",
    "get_registry_store",
    "kv_get",
    "kv_set",
    "record_to_agent_spec",
    "record_to_team",
    "team_to_record",
]
