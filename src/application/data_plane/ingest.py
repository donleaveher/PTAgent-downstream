"""将磁盘上的已保存文件登记为 :class:`DataObject`。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from pkg.data_plane.pipeline_paths import require_registered_pipeline_request
from pkg.data_plane.store import get_data_plane_store
from pkg.data_plane.types import DataType


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def infer_data_type_from_filename(name: str) -> DataType:
    suf = Path(name).suffix.lower()
    m = {".mgf": DataType.MGF, ".mzml": DataType.MZML, ".raw": DataType.RAW, ".fasta": DataType.FASTA, ".fa": DataType.FASTA, ".mztab": DataType.MZTAB}
    return m.get(suf, DataType.OTHER)


def register_file_as_data_object(
    absolute_path: Path,
    *,
    session_id: str | None,
    data_type: DataType | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    """
    在已有 session 上登记文件；无 session 时新建。

    返回 session_id, data_object_id, data_type, file_hash, file_size 等，供 API 与 Agent 使用。
    """
    store = get_data_plane_store()
    p = absolute_path.resolve()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    if request_id:
        require_registered_pipeline_request(request_id, store)
    if session_id:
        if not store.get_session(session_id):
            raise ValueError(f"unknown session_id: {session_id}")
        sid = session_id
    else:
        sid = store.create_session()
    dt = data_type or infer_data_type_from_filename(p.name)
    st = p.stat()
    hx = _sha256_file(p)
    meta: dict[str, Any] = {"filename": p.name, "source": "ingest"}
    oid = store.create_data_object(
        sid,
        dt,
        p,
        meta=meta,
        file_hash=hx,
        file_size=int(st.st_size),
        request_id=request_id,
    )
    out: dict[str, Any] = {
        "session_id": sid,
        "data_object_id": oid,
        "data_type": dt.value,
        "file_hash": hx,
        "file_size": int(st.st_size),
    }
    if request_id is not None:
        out["request_id"] = request_id
    return out
