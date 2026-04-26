"""
统一质谱批输入：客户端字段 → 内部规范字典（多谱、可导出 MGF / mzML）。

推荐客户端每条记录包含：

- **spectrum**：``[{ "mz", "intensity" }]``（或 ``m/z`` / ``i``）
- **precursorMz** / **precursor_mz**
- **precursorCharge** / **precursor_charge**（正整数）
- **actType** / **activation**：碎裂类型（如 CID、HCD）
- **retentionTime** / **retention_time**（秒，可选）
- **Name** / **name** / **spectrum_id**：谱图标识
- **species**（可选）
- **NCE** / **nce**（可选，数值）
- **instrument**（可选）
"""

from __future__ import annotations

from typing import Any


def _get(d: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def client_item_to_canonical(item: dict[str, Any], index: int = 0) -> dict[str, Any]:
    """
单条客户端记录 → 内部 ``SpectrumDict`` 兼容结构（键均为 snake_case 核心字段 + 可选元数据）。

    与 de novo / MCP Tool 侧 schema 校验兼容（同一套 SpectrumDict 约定）。
    （多余键保留，供导出 MGF/mzML 元数据）。
    """
    if not isinstance(item, dict):
        raise TypeError("batch item must be an object")
    peaks_raw = _get(item, "spectrum")
    if not isinstance(peaks_raw, list) or not peaks_raw:
        raise ValueError("spectrum must be a non-empty array of {mz, intensity}")
    pz: list[float] = []
    pi: list[float] = []
    for j, pt in enumerate(peaks_raw):
        if not isinstance(pt, dict):
            raise TypeError(f"spectrum[{j}] must be an object")
        mz = _get(pt, "mz", "m/z")
        it = _get(pt, "intensity", "i")
        if mz is None or it is None:
            raise ValueError(f"spectrum[{j}] needs mz and intensity")
        pz.append(float(mz))
        pi.append(float(it))

    pmz = _get(item, "precursorMz", "precursor_mz")
    ch = _get(item, "precursorCharge", "precursor_charge")
    if pmz is None:
        raise ValueError("precursorMz (or precursor_mz) is required")
    if ch is None:
        raise ValueError("precursorCharge (or precursor_charge) is required")
    ch_i = int(ch)
    if ch_i < 1:
        raise ValueError("precursorCharge must be >= 1")

    name = _get(item, "Name", "name", "spectrum_id")
    sid = str(name).strip() if name is not None else f"spectrum{index}"

    rt = _get(item, "retentionTime", "retention_time")
    act = _get(item, "actType", "act_type", "activation")
    species = _get(item, "species", "Species", "taxon")
    nce = _get(item, "NCE", "nce", "normalized_collision_energy")
    inst = _get(item, "instrument", "Instrument")

    out: dict[str, Any] = {
        "spectrum_id": sid,
        "precursor_mz": float(pmz),
        "precursor_charge": ch_i,
        "peaks_mz": pz,
        "peaks_intensity": pi,
    }
    if rt is not None:
        out["retention_time"] = float(rt)
    if act is not None:
        out["activation"] = str(act)
    if species is not None:
        out["species"] = str(species)
    if nce is not None:
        out["nce"] = float(nce)
    if inst is not None:
        out["instrument"] = str(inst)
    return out


def client_batch_to_canonical(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(items, list) or not items:
        raise ValueError("batch must be a non-empty array")
    return [client_item_to_canonical(x, i) for i, x in enumerate(items)]


__all__ = ["client_batch_to_canonical", "client_item_to_canonical"]
