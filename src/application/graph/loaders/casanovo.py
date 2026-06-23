"""Casanovo (de novo) → TrunkRow 装载器：mzTab 结果 + 输入谱图 按 index join。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pkg.data_plane.store import DataPlaneStore
from pkg.graph.types import TrunkRow
from pkg.ms_formats import parse_casanovo_mztab_psms, parse_mgf_spectra

# 这个 loader 负责的结果/谱图类型（按 data_type 选文件，别盲取第 0 个）
_RESULT_TYPES = {"MZTAB"}
_SPECTRA_TYPES = {"MGF", "MZML"}   # 目前只有 mgf 解析器；mzML 先占位


def _ids(run: dict[str, Any], key: str) -> list[str]:
    """input_object_ids / output_object_ids 在库里是 JSON 串，这里解开。"""
    return json.loads(run.get(key) or "[]")


def _pick(dp: DataPlaneStore, ids: list[str], types: set[str]) -> str | None:
    for oid in ids:
        obj = dp.get_data_object(oid)
        if obj and obj["data_type"] in types:
            return oid
    return None


def _sample_id_from(dp: DataPlaneStore, spectra_oid: str) -> tuple[str, str]:
    """从谱图文件 meta 推 sample_id / 展示名（稳定、可溯源即可）。"""
    obj = dp.get_data_object(spectra_oid) or {}
    meta = json.loads(obj.get("meta_json") or "{}")
    fname = meta.get("filename") or spectra_oid
    return f"sample:{Path(fname).stem}", Path(fname).stem


def build_rows(dp: DataPlaneStore, run: dict[str, Any]) -> list[TrunkRow]:
    spectra_oid = _pick(dp, _ids(run, "input_object_i" \
    "ds"), _SPECTRA_TYPES)
    result_oid  = _pick(dp, _ids(run, "output_object_ids"), _RESULT_TYPES)
    if not spectra_oid or not result_oid:
        return []   # 这个 run 不是 Casanovo 形态，跳过

    spectra = parse_mgf_spectra(dp.storage_path(spectra_oid))     # 顺序 = index
    psms    = parse_casanovo_mztab_psms(dp.storage_path(result_oid))  # index -> psm

    sample_id, sample_name = _sample_id_from(dp, spectra_oid)
    run_id = run["run_id"]
    rows: list[TrunkRow] = []

    for idx, spec in enumerate(spectra):
        psm = psms.get(idx)
        if psm is None:           # 该谱无预测 → 主干这条不挂（也可选择只建 Spectrum）
            continue
        seq = psm["sequence"]
        peptidoform = psm["proforma"] or seq        # 带修饰优先；空则退裸序列
        rows.append(TrunkRow(
            # —— 谱图侧 ——
            spectrum_id=f"{spectra_oid}:{idx}",      # 全局唯一稳定键（文件+index）
            precursor_mz=spec["precursor_mz"],
            charge=spec["precursor_charge"],
            retention_time=None,                     # ⚠️ mgf 解析器暂不给 RT，先 None
            scan_index=idx,
            spectra_object_id=spectra_oid,
            # —— 结果侧 ——
            psm_id=f"{result_oid}:{idx}",            # 全局唯一
            score=psm["score"],
            q_value=None,                            # de novo 无 FDR
            aa_scores=psm["aa_scores"],
            search_engine="casanovo",
            is_decoy=False,                          # de novo 无 decoy
            result_object_id=result_oid,
            # —— 肽段 ——
            peptidoform=peptidoform,
            stripped_sequence=seq,
            length=len(seq),
            # —— 上下文 ——
            sample_id=sample_id,
            sample_name=sample_name,
            condition="",
            run_id=run_id,
        ))
    return rows