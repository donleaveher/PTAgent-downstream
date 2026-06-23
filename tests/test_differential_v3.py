"""L2 差异分析：引擎（log2FC + Welch t + BH）与应用服务。"""

from __future__ import annotations

from application.analysis import analyze_experiment_differential
from pkg.analysis import compute_differential_results
from pkg.experiment import (
    DifferentialDirection,
    InMemoryExperimentRepository,
    ProteinQuantification,
    ingest_experiment_payload,
)
from tests.pkg.test_experiment_models import valid_payload


def _quant(experiment_id: str, protein_id: str, group_id: str, values: list[float]):
    return [
        ProteinQuantification(
            experiment_id=experiment_id,
            protein_id=protein_id,
            group_id=group_id,
            sample_id=f"{group_id}_s{i}",
            abundance=v,
        )
        for i, v in enumerate(values)
    ]


def test_engine_flags_up_down_and_not_significant() -> None:
    quant = (
        _quant("e", "UP", "case", [100, 110, 90])
        + _quant("e", "UP", "ctrl", [10, 12, 8])
        + _quant("e", "FLAT", "case", [10, 11, 9])
        + _quant("e", "FLAT", "ctrl", [10, 9, 11])
        + _quant("e", "DOWN", "case", [5, 6, 4])
        + _quant("e", "DOWN", "ctrl", [50, 55, 45])
    )
    results = {
        r.protein_id: r
        for r in compute_differential_results(
            quant, experiment_id="e", case_group_id="case", control_group_id="ctrl"
        )
    }
    assert results["UP"].is_differential and results["UP"].direction is DifferentialDirection.UP
    assert results["UP"].log2fc > 3
    assert results["DOWN"].is_differential and results["DOWN"].direction is DifferentialDirection.DOWN
    assert not results["FLAT"].is_differential
    assert results["UP"].q_value is not None and results["UP"].q_value <= 0.05


def test_engine_no_replicate_falls_back_to_fold_change() -> None:
    quant = _quant("e", "P", "case", [100]) + _quant("e", "P", "ctrl", [10])
    (result,) = compute_differential_results(
        quant, experiment_id="e", case_group_id="case", control_group_id="ctrl"
    )
    assert result.p_value is None and result.q_value is None
    assert result.is_differential and result.direction is DifferentialDirection.UP


def test_engine_skips_proteins_missing_a_group() -> None:
    quant = _quant("e", "ONLY_CASE", "case", [100, 90])  # 无对照组 → 跳过
    assert compute_differential_results(
        quant, experiment_id="e", case_group_id="case", control_group_id="ctrl"
    ) == []


def test_service_persists_and_summarizes() -> None:
    repo = InMemoryExperimentRepository()
    payload = valid_payload()  # groups g_case(case)/g_ctrl(control), protein prot_1
    payload["proteins"].append(
        {"protein_id": "prot_2", "accession": "Q2", "gene": "G2", "peptide_ids": []}
    )
    ingest_experiment_payload(payload, repo)
    repo.add_quantifications(
        _quant("exp_1", "prot_1", "g_case", [100, 120, 110])
        + _quant("exp_1", "prot_1", "g_ctrl", [10, 9, 11])
        + _quant("exp_1", "prot_2", "g_case", [10, 11, 9])
        + _quant("exp_1", "prot_2", "g_ctrl", [10, 9, 11])
    )

    summary = analyze_experiment_differential("exp_1", repository=repo)  # 自动按 role 选组

    assert summary["case_group_id"] == "g_case" and summary["control_group_id"] == "g_ctrl"
    assert summary["proteins_tested"] == 2
    assert summary["differential"] == 1 and summary["up"] == 1
    diff = {d.protein_id: d for d in repo.list_differentials("exp_1")}
    assert diff["prot_1"].is_differential and not diff["prot_2"].is_differential
