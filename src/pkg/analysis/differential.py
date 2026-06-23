"""蛋白级差异分析（case vs control）。

纯函数：吃定量(ProteinQuantification)，出 DifferentialResult。
log2FC（均值比）+ Welch t 检验（对 log 强度）+ BH FDR。无重复时退化为只看 fold change。
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
from scipy import stats

from pkg.experiment.types import (
    DifferentialDirection,
    DifferentialResult,
    ProteinQuantification,
)


def compute_differential_results(
    quantifications: list[ProteinQuantification],
    *,
    experiment_id: str,
    case_group_id: str,
    control_group_id: str,
    log2fc_threshold: float = 1.0,
    q_threshold: float = 0.05,
    min_samples: int = 2,
    log_transform: bool = True,
) -> list[DifferentialResult]:
    """返回每个可比较蛋白的差异结果（已按 protein_id 排序）。"""

    grouped: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: {"case": [], "control": []}
    )
    for quant in quantifications:
        if quant.experiment_id != experiment_id:
            continue
        if quant.group_id == case_group_id:
            grouped[quant.protein_id]["case"].append(quant.abundance)
        elif quant.group_id == control_group_id:
            grouped[quant.protein_id]["control"].append(quant.abundance)

    # 第一遍：log2FC + p 值
    staged: list[tuple[str, float, float | None]] = []
    for protein_id in sorted(grouped):
        case = [v for v in grouped[protein_id]["case"] if v > 0]
        control = [v for v in grouped[protein_id]["control"] if v > 0]
        if not case or not control:
            continue  # 任一组缺值 → 无法比较
        case_arr = np.asarray(case, dtype=float)
        control_arr = np.asarray(control, dtype=float)
        log2fc = math.log2(case_arr.mean()) - math.log2(control_arr.mean())
        p_value: float | None = None
        if len(case) >= min_samples and len(control) >= min_samples:
            left = np.log2(case_arr) if log_transform else case_arr
            right = np.log2(control_arr) if log_transform else control_arr
            pvalue = stats.ttest_ind(left, right, equal_var=False).pvalue
            p_value = float(pvalue) if np.isfinite(pvalue) else None
        staged.append((protein_id, log2fc, p_value))

    # BH 校正（仅对有 p 值的蛋白）
    with_p = [i for i, row in enumerate(staged) if row[2] is not None]
    q_by_index: dict[int, float] = {}
    if with_p:
        qvals = stats.false_discovery_control([staged[i][2] for i in with_p], method="bh")
        q_by_index = {i: float(q) for i, q in zip(with_p, qvals)}

    results: list[DifferentialResult] = []
    for index, (protein_id, log2fc, p_value) in enumerate(staged):
        q_value = q_by_index.get(index)
        passes_fc = abs(log2fc) >= log2fc_threshold
        # 有 p 值 → 要求 q 显著；无重复 → 退化为只看 fold change
        passes_sig = (q_value is not None and q_value <= q_threshold) if p_value is not None else True
        is_differential = passes_fc and passes_sig
        if not is_differential:
            direction = DifferentialDirection.NOT_SIGNIFICANT
        elif log2fc > 0:
            direction = DifferentialDirection.UP
        else:
            direction = DifferentialDirection.DOWN
        results.append(
            DifferentialResult(
                experiment_id=experiment_id,
                protein_id=protein_id,
                case_group_id=case_group_id,
                control_group_id=control_group_id,
                log2fc=log2fc,
                p_value=p_value,
                q_value=q_value,
                direction=direction,
                is_differential=is_differential,
            )
        )
    return results


__all__ = ["compute_differential_results"]
