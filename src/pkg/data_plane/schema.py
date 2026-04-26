"""SQLite 表结构；与迁移逻辑（为已有库加列/加表）。"""

from __future__ import annotations

import sqlite3

_BASE = """
CREATE TABLE IF NOT EXISTS dp_session (
  session_id TEXT PRIMARY KEY NOT NULL,
  user_id TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  current_cursor_id TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dp_data_object (
  object_id TEXT PRIMARY KEY NOT NULL,
  session_id TEXT NOT NULL,
  data_type TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  meta_json TEXT NOT NULL DEFAULT '{}',
  file_hash TEXT,
  file_size INTEGER,
  FOREIGN KEY (session_id) REFERENCES dp_session(session_id)
);

CREATE INDEX IF NOT EXISTS idx_dp_data_object_session ON dp_data_object(session_id);

CREATE TABLE IF NOT EXISTS dp_run (
  run_id TEXT PRIMARY KEY NOT NULL,
  session_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  run_kind TEXT NOT NULL DEFAULT 'FILE_PIPELINE',
  status TEXT NOT NULL DEFAULT 'Pending',
  input_object_ids TEXT NOT NULL DEFAULT '[]',
  output_object_ids TEXT NOT NULL DEFAULT '[]',
  parameters TEXT NOT NULL DEFAULT '{}',
  error_log TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT,
  FOREIGN KEY (session_id) REFERENCES dp_session(session_id)
);

CREATE INDEX IF NOT EXISTS idx_dp_run_session ON dp_run(session_id);

CREATE TABLE IF NOT EXISTS dp_pipeline_request (
  request_id TEXT PRIMARY KEY NOT NULL,
  session_id TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  root_path TEXT NOT NULL,
  meta_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT,
  FOREIGN KEY (session_id) REFERENCES dp_session(session_id)
);

CREATE INDEX IF NOT EXISTS idx_dp_pipeline_session ON dp_pipeline_request(session_id);
"""


def _try_alter_column(conn: sqlite3.Connection, table: str, column: str, col_type: str) -> None:
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
    except sqlite3.OperationalError as e:
        if "duplicate column" not in str(e).lower():
            if "add column" in str(e).lower() or "duplicate" in str(e).lower():
                return
            raise


def _migrate_v2(conn: sqlite3.Connection) -> None:
    for t, c, typ in (("dp_data_object", "request_id", "TEXT"), ("dp_run", "request_id", "TEXT")):
        _try_alter_column(conn, t, c, typ)


def apply_data_plane_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_BASE)
    _migrate_v2(conn)
    conn.execute(
        "INSERT OR IGNORE INTO dp_session (session_id, user_id, status) VALUES (?, NULL, 'active')",
        ("dp-system",),
    )
