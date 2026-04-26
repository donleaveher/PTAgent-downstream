"""SQLite 注册表读写。"""

from __future__ import annotations

from pathlib import Path

from application.agent.store import SqliteAgentRegistryStore, kv_get, kv_set


def test_sqlite_agent_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    s = SqliteAgentRegistryStore(db)
    s.upsert_agent(
        {
            "key": "a1",
            "name": "n",
            "description": "",
            "mcp_categories": None,
            "mcp_tool_allowlist": None,
            "system_prompt": "p",
            "rag_profile_id": None,
            "llm_model": "gpt-4o-mini",
            "llm_temperature": 0.2,
            "interaction_mode": "freeform",
            "meta": {},
        }
    )
    s2 = SqliteAgentRegistryStore(db)
    assert s2.get_agent_record("a1") is not None
    assert s2.get_agent_record("a1")["name"] == "n"


def test_kv_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "kv.db"
    assert kv_get(db, "k") is None
    kv_set(db, "k", '{"x":1}')
    assert kv_get(db, "k") == '{"x":1}'
