"""数据平面：Session / DataObject / Run 的 SQLite 存取；供 FastAPI 与（同库文件路径）学习子进程共用。"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from config.database_settings import resolve_database_path
from .schema import apply_data_plane_schema
from .types import DataType, RunKind, RunStatus, SYSTEM_SESSION_ID


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()


class DataPlaneStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._init_db()

    @property
    def db_path(self) -> Path:
        return self._path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            apply_data_plane_schema(conn)

    def create_session(self, user_id: str | None = None) -> str:
        sid = _new_id("sess")
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO dp_session (session_id, user_id, status) VALUES (?, ?, 'active')",
                    (sid, user_id),
                )
        return sid

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT session_id, user_id, status, current_cursor_id, created_at FROM dp_session WHERE session_id=?",
                    (session_id,),
                ).fetchone()
                if not row:
                    return None
                return dict(row)

    def set_session_cursor(self, session_id: str, current_cursor_id: str | None) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE dp_session SET current_cursor_id=? WHERE session_id=?",
                    (current_cursor_id, session_id),
                )

    def create_data_object(
        self,
        session_id: str,
        data_type: DataType,
        storage_path: Path,
        *,
        meta: dict[str, Any] | None = None,
        file_hash: str | None = None,
        file_size: int | None = None,
        request_id: str | None = None,
    ) -> str:
        oid = _new_id("dobj")
        p = str(Path(storage_path).resolve())
        meta_json = json.dumps(meta or {}, ensure_ascii=False)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO dp_data_object
                    (object_id, session_id, data_type, storage_path, meta_json, file_hash, file_size, request_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (oid, session_id, data_type.value, p, meta_json, file_hash, file_size, request_id),
                )
        return oid

    def get_data_object(self, object_id: str) -> dict[str, Any] | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM dp_data_object WHERE object_id=?", (object_id,)).fetchone()
                if not row:
                    return None
                return dict(row)

    def storage_path(self, object_id: str) -> Path | None:
        row = self.get_data_object(object_id)
        if not row:
            return None
        return Path(row["storage_path"])

    def create_run(
        self,
        session_id: str,
        tool_name: str,
        *,
        run_kind: RunKind = RunKind.FILE_PIPELINE,
        input_object_ids: Sequence[str] | None = None,
        parameters: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> str:
        rid = _new_id("run")
        ins = list(input_object_ids or [])
        par = parameters or {}
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO dp_run
                    (run_id, session_id, tool_name, run_kind, status, input_object_ids, output_object_ids, parameters, updated_at, request_id)
                    VALUES (?, ?, ?, ?, ?, ?, '[]', ?, ?, ?)
                    """,
                    (
                        rid,
                        session_id,
                        tool_name,
                        run_kind.value,
                        RunStatus.PENDING.value,
                        json.dumps(ins, ensure_ascii=False),
                        json.dumps(par, ensure_ascii=False),
                        _now_iso(),
                        request_id,
                    ),
                )
        return rid

    def update_run(
        self,
        run_id: str,
        *,
        status: RunStatus | None = None,
        output_object_ids: Sequence[str] | None = None,
        error_log: str | None = None,
    ) -> None:
        outs = list(output_object_ids) if output_object_ids is not None else None
        with self._lock:
            with self._connect() as conn:
                st = status.value if status is not None else None
                if st is not None and outs is not None:
                    conn.execute(
                        """
                        UPDATE dp_run
                        SET status=?, output_object_ids=?, error_log=?, updated_at=?
                        WHERE run_id=?
                        """,
                        (st, json.dumps(outs, ensure_ascii=False), error_log, _now_iso(), run_id),
                    )
                elif st is not None:
                    conn.execute(
                        "UPDATE dp_run SET status=?, error_log=?, updated_at=? WHERE run_id=?",
                        (st, error_log, _now_iso(), run_id),
                    )
                elif outs is not None:
                    conn.execute(
                        "UPDATE dp_run SET output_object_ids=?, updated_at=? WHERE run_id=?",
                        (json.dumps(outs, ensure_ascii=False), _now_iso(), run_id),
                    )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM dp_run WHERE run_id=?", (run_id,)).fetchone()
                if not row:
                    return None
                return dict(row)

    def create_pipeline_request(
        self,
        request_id: str,
        root_path: Path,
        *,
        session_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        p = str(Path(root_path).resolve())
        m = json.dumps(meta or {}, ensure_ascii=False)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO dp_pipeline_request
                    (request_id, session_id, status, root_path, meta_json, updated_at)
                    VALUES (?, ?, 'open', ?, ?, ?)
                    """,
                    (request_id, session_id, p, m, _now_iso()),
                )

    def get_pipeline_request(self, request_id: str) -> dict[str, Any] | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM dp_pipeline_request WHERE request_id=?", (request_id,)).fetchone()
                if not row:
                    return None
                return dict(row)

    def list_data_object_ids_by_request(self, request_id: str) -> list[str]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT object_id FROM dp_data_object WHERE request_id=? ORDER BY object_id",
                    (request_id,),
                ).fetchall()
                return [str(r[0]) for r in rows]


_data_plane_store: DataPlaneStore | None = None


def get_data_plane_store() -> DataPlaneStore:
    global _data_plane_store
    if _data_plane_store is None:
        _data_plane_store = DataPlaneStore(resolve_database_path())
    return _data_plane_store


__all__ = [
    "DataPlaneStore",
    "get_data_plane_store",
    "SYSTEM_SESSION_ID",
]
