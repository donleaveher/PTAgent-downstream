"""MCP 控制台工具示例参数（仅 SQLite kv）。"""

from __future__ import annotations

import json

from application.agent.store import kv_set
from application.mcp_tool_arg_presets import merge_tool_arg_presets


def test_merge_empty_without_seed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PTAGENT_DATABASE__SQLITE_PATH", str(tmp_path / "db.db"))
    from config.settings import get_settings

    get_settings.cache_clear()
    merged, stored = merge_tool_arg_presets()
    get_settings.cache_clear()
    assert merged == {}
    assert stored == {}


def test_merge_reads_kv(tmp_path, monkeypatch) -> None:
    db = tmp_path / "x.db"
    monkeypatch.setenv("PTAGENT_DATABASE__SQLITE_PATH", str(db))
    from config.settings import get_settings

    get_settings.cache_clear()
    kv_set(db, "mcp_tool_arg_presets", json.dumps({"t1": {"a": 1}}, ensure_ascii=False))
    merged, _ = merge_tool_arg_presets()
    get_settings.cache_clear()
    assert merged.get("t1") == {"a": 1}
