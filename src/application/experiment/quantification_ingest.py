"""定量数据摄入应用服务（下游自定义契约 · INPUT-CONTRACT §6）。

定量与 bundle 的定性输入分离：实验创建后可单独、增量提交一批
``{protein_id, group_id, sample_id, abundance}``。落库 ``ProteinQuantification``
即解锁 L2 蛋白级差异分析（``analyze_experiment_differential``）。

校验：实验存在；每行 ``protein_id`` ∈ 实验蛋白、``group_id`` ∈ 实验分组。
任一行不合法 → 整批拒绝（不部分落库），抛 ``QuantificationIngestError``。
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from pkg.experiment import (
    ExperimentRepository,
    ProteinQuantification,
    get_experiment_store,
)


class QuantificationIngestError(ValueError):
    """定量行非法：字段校验失败，或引用了该实验不存在的 protein_id / group_id。"""


def ingest_experiment_quantifications(
    experiment_id: str,
    rows: list[dict[str, Any]],
    *,
    repository: ExperimentRepository | None = None,
) -> dict[str, Any]:
    """校验并持久化一批蛋白定量行。

    与 ``add_quantifications`` 一致按 ``(protein_id, group_id, sample_id)`` 去重：
    重复提交同一三元组等于覆盖该样本丰度（幂等 upsert）。

    Raises:
        ValueError: 实验不存在（由调用方/路由转 404）。
        QuantificationIngestError: 存在非法行（转 422），消息含每行错误位置。
    """

    repo = repository or get_experiment_store()
    if repo.get_context(experiment_id) is None:
        raise ValueError(f"unknown experiment_id: {experiment_id}")

    known_proteins = {p.protein_id for p in repo.list_proteins(experiment_id)}
    known_groups = {g.group_id for g in repo.list_groups(experiment_id)}

    parsed: list[ProteinQuantification] = []
    errors: list[str] = []
    for index, row in enumerate(rows):
        # 行内若自带 experiment_id，必须与 URL 路径一致，防跨实验串写。
        row_eid = row.get("experiment_id")
        if row_eid is not None and row_eid != experiment_id:
            errors.append(
                f"row[{index}]: experiment_id {row_eid!r} does not match {experiment_id!r}"
            )
            continue
        try:
            quant = ProteinQuantification.model_validate({**row, "experiment_id": experiment_id})
        except ValidationError as exc:
            errors.append(f"row[{index}]: {_summarize_validation(exc)}")
            continue

        bad_refs: list[str] = []
        if quant.protein_id not in known_proteins:
            bad_refs.append(f"unknown protein_id {quant.protein_id!r}")
        if quant.group_id not in known_groups:
            bad_refs.append(f"unknown group_id {quant.group_id!r}")
        if bad_refs:
            errors.append(f"row[{index}]: " + "; ".join(bad_refs))
            continue

        parsed.append(quant)

    if errors:
        raise QuantificationIngestError(
            f"{len(errors)} invalid quantification row(s): " + " | ".join(errors)
        )

    written = repo.add_quantifications(parsed)
    return {
        "experiment_id": experiment_id,
        "received": len(rows),
        "written": written,
        "proteins": len({q.protein_id for q in parsed}),
        "groups": len({q.group_id for q in parsed}),
        "samples": len({q.sample_id for q in parsed}),
    }


def _summarize_validation(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        parts.append(f"{loc} {err['msg']}")
    return "; ".join(parts)


__all__ = ["QuantificationIngestError", "ingest_experiment_quantifications"]
