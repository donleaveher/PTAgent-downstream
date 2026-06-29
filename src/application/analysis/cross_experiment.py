"""跨实验比较：把多个实验的差异蛋白 / 疾病结论按稳定键对齐（§11.1）。

``protein_id`` 是实验内局部 id、跨实验不可比；故差异蛋白按 **UniProt accession** 对齐，
疾病关联按 **disease_id** 对齐。回答"哪些蛋白/疾病在多个实验里反复出现、哪些是某实验独有"。
纯读多实验事实，确定性输出（列表有序），不写库。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pkg.experiment import (
    EvidenceLevel,
    ExperimentRepository,
    get_experiment_store,
)


def compare_experiments(
    experiment_ids: Iterable[str],
    *,
    repository: ExperimentRepository | None = None,
) -> dict[str, Any]:
    """对比 ≥2 个实验的差异蛋白（按 accession）与疾病结论（按 disease_id）。

    Raises:
        ValueError: 少于 2 个实验，或存在未知 experiment_id（由路由分别转 400 / 404）。
    """

    repo = repository or get_experiment_store()
    ids = list(dict.fromkeys(experiment_ids))  # 去重保序
    if len(ids) < 2:
        raise ValueError("compare_experiments needs at least 2 distinct experiment_ids")
    unknown = [eid for eid in ids if repo.get_context(eid) is None]
    if unknown:
        raise ValueError(f"unknown experiment_id(s): {unknown}")

    diff_by_acc: dict[str, list[str]] = {}
    disease_by_id: dict[str, dict[str, Any]] = {}
    per_experiment: dict[str, dict[str, int]] = {}

    for eid in ids:
        acc_by_pid = {p.protein_id: p.accession for p in repo.list_proteins(eid)}
        diff_accs = {
            acc_by_pid[d.protein_id]
            for d in repo.list_differentials(eid)
            if d.is_differential and acc_by_pid.get(d.protein_id)
        }
        for acc in diff_accs:
            diff_by_acc.setdefault(acc, [])
            if eid not in diff_by_acc[acc]:
                diff_by_acc[acc].append(eid)

        diseases_here: set[str] = set()
        for ann in repo.list_annotations(eid):
            if (
                ann.evidence_level is EvidenceLevel.CONCLUSION
                and str(ann.attribute).startswith("disease:")
                and isinstance(ann.value, dict)
                and ann.value.get("disease_id")
            ):
                disease_id = ann.value["disease_id"]
                entry = disease_by_id.setdefault(
                    disease_id,
                    {"name": ann.value.get("disease_name", ""), "experiments": []},
                )
                if eid not in entry["experiments"]:
                    entry["experiments"].append(eid)
                diseases_here.add(disease_id)

        per_experiment[eid] = {
            "differential_proteins": len(diff_accs),
            "disease_conclusions": len(diseases_here),
        }

    n = len(ids)
    return {
        "experiment_ids": ids,
        "per_experiment": per_experiment,
        "differential_proteins": {
            "by_accession": {acc: diff_by_acc[acc] for acc in sorted(diff_by_acc)},
            "shared_in_all": sorted(a for a, es in diff_by_acc.items() if len(es) == n),
        },
        "disease_conclusions": {
            "by_disease": {did: disease_by_id[did] for did in sorted(disease_by_id)},
            "shared_in_all": sorted(
                d for d, e in disease_by_id.items() if len(e["experiments"]) == n
            ),
        },
    }


__all__ = ["compare_experiments"]
