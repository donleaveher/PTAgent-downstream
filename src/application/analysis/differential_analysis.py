"""差异分析应用服务：读定量 → 算差异 → 落库。"""

from __future__ import annotations

from typing import Any

from pkg.analysis import compute_differential_results
from pkg.experiment import (
    DifferentialDirection,
    ExperimentRepository,
    GroupRole,
    get_experiment_store,
)


def analyze_experiment_differential(
    experiment_id: str,
    *,
    case_group_id: str | None = None,
    control_group_id: str | None = None,
    repository: ExperimentRepository | None = None,
    log2fc_threshold: float = 1.0,
    q_threshold: float = 0.05,
    min_samples: int = 2,
) -> dict[str, Any]:
    """case vs control 蛋白级差异，写入 DifferentialResult。

    未显式给组时，按 role 自动选唯一的 case / control 组。
    """

    repo = repository or get_experiment_store()
    context = repo.get_context(experiment_id)
    if context is None:
        raise ValueError(f"unknown experiment_id: {experiment_id}")

    groups = repo.list_groups(experiment_id)
    if case_group_id is None:
        case_group_id = _single_group(groups, GroupRole.CASE)
    if control_group_id is None:
        control_group_id = _single_group(groups, GroupRole.CONTROL)

    quantifications = repo.list_quantifications(experiment_id)
    results = compute_differential_results(
        quantifications,
        experiment_id=experiment_id,
        case_group_id=case_group_id,
        control_group_id=control_group_id,
        log2fc_threshold=log2fc_threshold,
        q_threshold=q_threshold,
        min_samples=min_samples,
    )
    written = repo.add_differentials(results)
    differential = [r for r in results if r.is_differential]
    return {
        "experiment_id": experiment_id,
        "case_group_id": case_group_id,
        "control_group_id": control_group_id,
        "proteins_tested": len(results),
        "differential": len(differential),
        "up": sum(1 for r in differential if r.direction is DifferentialDirection.UP),
        "down": sum(1 for r in differential if r.direction is DifferentialDirection.DOWN),
        "written": written,
    }


def _single_group(groups: list, role: GroupRole) -> str:
    matches = [g.group_id for g in groups if g.role is role]
    if len(matches) != 1:
        raise ValueError(
            f"need exactly one {role.value} group to auto-select; found {len(matches)} "
            f"(pass case_group_id/control_group_id explicitly)"
        )
    return matches[0]


__all__ = ["analyze_experiment_differential"]
