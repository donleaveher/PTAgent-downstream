"""Agent / Team 与 KV — 统一 SQLite 存储（产品侧；校验图结构依赖 ``pkg.agent`` 内核）。"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from pkg.agent._internal.team_graph import validate_team_graph
from pkg.data_plane.schema import apply_data_plane_schema

from .records import (
    agent_spec_to_record,
    record_to_agent_spec,
    record_to_team,
    team_to_record,
)

_KV_LOCK = threading.RLock()


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS agents (
            key TEXT PRIMARY KEY NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS teams (
            key TEXT PRIMARY KEY NOT NULL,
            payload TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kv (
            key TEXT PRIMARY KEY NOT NULL,
            value TEXT NOT NULL
        )
        """
    )
    apply_data_plane_schema(conn)


def ensure_database_schema(path: Path) -> None:
    """若库不存在则创建并建表（供 KV 早于 Agent 单例访问）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path), timeout=30.0, isolation_level=None) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        _create_tables(conn)


def kv_get(path: Path, key: str) -> str | None:
    ensure_database_schema(path)
    with _KV_LOCK:
        with sqlite3.connect(str(path), timeout=30.0, isolation_level=None) as conn:
            row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
            return str(row[0]) if row else None


def kv_set(path: Path, key: str, value: str) -> None:
    ensure_database_schema(path)
    with _KV_LOCK:
        with sqlite3.connect(str(path), timeout=30.0, isolation_level=None) as conn:
            conn.execute(
                "INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )


class SqliteAgentRegistryStore:
    """线程安全 SQLite；agents / teams 行存 JSON payload。"""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @property
    def path(self) -> Path:
        return self._path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            _create_tables(conn)

    def _load_all_agents(self, conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for row in conn.execute("SELECT key, payload FROM agents"):
            try:
                d = json.loads(row["payload"])
                if isinstance(d, dict) and d.get("key"):
                    out[str(d["key"])] = d
            except json.JSONDecodeError:
                continue
        return out

    def _load_all_teams(self, conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for row in conn.execute("SELECT key, payload FROM teams"):
            try:
                d = json.loads(row["payload"])
                if isinstance(d, dict) and d.get("key"):
                    out[str(d["key"])] = d
            except json.JSONDecodeError:
                continue
        return out

    def list_agent_records(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            with self._connect() as conn:
                return self._load_all_agents(conn)

    def get_agent_record(self, key: str) -> dict[str, Any] | None:
        return self.list_agent_records().get(key)

    def upsert_agent(self, record: dict[str, Any]) -> None:
        spec = record_to_agent_spec(record)
        key = spec.key
        payload = json.dumps(agent_spec_to_record(spec), ensure_ascii=False)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO agents(key, payload) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload",
                    (key, payload),
                )

    def delete_agent(self, key: str) -> bool:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute("DELETE FROM agents WHERE key=?", (key,))
                if cur.rowcount == 0:
                    return False
                for row in conn.execute("SELECT key, payload FROM teams"):
                    try:
                        tv = json.loads(row["payload"])
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(tv, dict):
                        continue
                    lo = tv.get("linear_order") or []
                    if isinstance(lo, list) and key in lo:
                        tv["linear_order"] = [x for x in lo if x != key]
                        conn.execute(
                            "UPDATE teams SET payload=? WHERE key=?",
                            (json.dumps(tv, ensure_ascii=False), row["key"]),
                        )
                return True

    def list_team_records(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            with self._connect() as conn:
                return self._load_all_teams(conn)

    def upsert_team(self, record: dict[str, Any]) -> None:
        team = record_to_team(record)
        has_nodes = isinstance(team.graph, dict) and bool(team.graph.get("nodes"))
        has_linear = bool(team.linear_order)
        if has_nodes or has_linear:
            g = team.resolved_graph()
            errs = validate_team_graph(g)
            if errs:
                raise ValueError("; ".join(errs))
        key = team.key
        payload = json.dumps(team_to_record(team), ensure_ascii=False)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO teams(key, payload) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload",
                    (key, payload),
                )

    def delete_team(self, key: str) -> bool:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute("DELETE FROM teams WHERE key=?", (key,))
                return cur.rowcount > 0


__all__ = [
    "SqliteAgentRegistryStore",
    "ensure_database_schema",
    "kv_get",
    "kv_set",
]
