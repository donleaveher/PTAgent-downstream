"""数据平面表与登记逻辑。"""

from __future__ import annotations

from pathlib import Path

from pkg.data_plane.store import DataPlaneStore
from pkg.data_plane.types import DataType, RunStatus, SYSTEM_SESSION_ID


def test_data_plane_session_and_object(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    store = DataPlaneStore(db)
    assert store.get_session(SYSTEM_SESSION_ID) is not None

    sid = store.create_session()
    f = tmp_path / "a.mgf"
    f.write_text("BEGIN IONS\nEND IONS\n", encoding="utf-8")
    oid = store.create_data_object(
        sid,
        DataType.MGF,
        f,
        meta={"n": 1},
        file_size=f.stat().st_size,
    )
    row = store.get_data_object(oid)
    assert row is not None
    assert row["session_id"] == sid
    assert Path(row["storage_path"]) == f.resolve()

    rid = store.create_run(sid, "t", input_object_ids=[oid])
    store.update_run(rid, status=RunStatus.SUCCESS, output_object_ids=[oid])
    r2 = store.get_run(rid)
    assert r2 is not None
    assert r2["status"] == RunStatus.SUCCESS.value


def test_pipeline_request_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    store = DataPlaneStore(db)
    prq = f"prq_{'a' * 12}"
    store.create_pipeline_request(prq, tmp_path / "root", meta={"n": 1})
    row = store.get_pipeline_request(prq)
    assert row is not None
    assert row["request_id"] == prq
    f = tmp_path / "f.mgf"
    f.write_text("x", encoding="utf-8")
    oid1 = store.create_data_object(
        store.create_session(),
        DataType.MGF,
        f,
        meta={},
        file_size=1,
        request_id=prq,
    )
    ids = store.list_data_object_ids_by_request(prq)
    assert oid1 in ids
