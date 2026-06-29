"""实验冻结归档：把验证完成的本次实验冻结为只读版本化快照（§9）。

冻结前检查 →（输入/Meta/历史/差异/图投影摘要/版本）确定性 manifest → 稳定 checksum →
`ExperimentSnapshot(FINAL)`。manifest 捕获冻结时的内容，因此 deep-search 之后再改动事实，
旧快照读回仍保持不变；checksum 提供篡改检测。版本唯一由仓库（应用层）+ DDL `UNIQUE`
（数据库层）双重阻止覆盖；新证据创建新版本，不修改旧快照（不物理删除历史）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from application.graph.project_kg import project_experiment_kg
from pkg.experiment import (
    AnnotationTargetType,
    EvidenceLevel,
    ExperimentRepository,
    ExperimentSnapshot,
    ExperimentStatus,
    get_experiment_store,
)
from pkg.graph import InMemoryGraphStore

_PROVENANCE_VERSION_KEYS = (
    "db_version",
    "source_version",
    "ctd_version",
    "structure_version",
    "version",
)


class FreezePreconditionError(ValueError):
    """冻结前置条件未满足（如存在未经 deep-search 处理的假说）。"""


def _canonical(obj: Any) -> str:
    return json.dumps(
        obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )


def compute_manifest_checksum(manifest: dict[str, Any]) -> str:
    """对 manifest 计算稳定 SHA-256（不含 frozen_at 等易变字段）。"""

    return hashlib.sha256(_canonical(manifest).encode("utf-8")).hexdigest()


def verify_snapshot_integrity(snapshot: ExperimentSnapshot) -> bool:
    """重算 manifest checksum 并与快照存储值比对（篡改检测）。"""

    return bool(snapshot.manifest) and (
        compute_manifest_checksum(snapshot.manifest) == snapshot.checksum
    )


def freeze_experiment(
    experiment_id: str,
    *,
    snapshot_version: str,
    pipeline_version: str,
    repository: ExperimentRepository | None = None,
    model_version: str | None = None,
    query_and_params: dict[str, Any] | None = None,
    report_artifact_ref: str = "",
    allow_unresolved_hypotheses: bool = False,
    supersede_prior: bool = True,
) -> ExperimentSnapshot:
    """冻结一个实验为只读快照；版本重复将被仓库拒绝（阻止覆盖）。

    `supersede_prior=True`（默认）：新版本生效后，把该实验其余 FINAL 快照标
    `SUPERSEDED`（不删，旧版仍可读、仍自洽），使"当前版本"唯一。
    """

    repo = repository or get_experiment_store()
    context = repo.get_context(experiment_id)
    if context is None:
        raise ValueError(f"unknown experiment_id: {experiment_id}")

    proteins = repo.list_proteins(experiment_id)
    peptides = repo.list_peptides(experiment_id)
    groups = repo.list_groups(experiment_id)
    annotations = repo.list_annotations(experiment_id)
    history = repo.list_annotation_history(experiment_id)
    differentials = repo.list_differentials(experiment_id)
    enrichments = repo.list_enrichments(experiment_id)

    # 冻结前检查：每条蛋白级疾病假说都应已被 deep-search 处理（留有历史），否则未决不明
    history_annotation_ids = {h.annotation_id for h in history}
    unprocessed = sorted(
        ann.annotation_id
        for ann in annotations
        if ann.evidence_level is EvidenceLevel.HYPOTHESIS
        and ann.target_type is AnnotationTargetType.PROTEIN
        and ann.annotation_id not in history_annotation_ids
    )
    if unprocessed and not allow_unresolved_hypotheses:
        raise FreezePreconditionError(
            f"{len(unprocessed)} hypotheses not processed by deep-search "
            f"(e.g. {unprocessed[:3]}); run deep-search or pass allow_unresolved_hypotheses=True"
        )

    # 来源版本：从注释 provenance 归集（CTD/UniProt/Foldseek 等）
    source_versions: dict[str, str] = {}
    for ann in annotations:
        prov = ann.provenance or {}
        version = next(
            (str(prov[key]) for key in _PROVENANCE_VERSION_KEYS if prov.get(key)), ""
        )
        if version and ann.source not in source_versions:
            source_versions[ann.source] = version

    # 图投影摘要：投到临时内存图库，不触碰生产图库
    graph_summary = project_experiment_kg(
        experiment_id, repository=repo, store=InMemoryGraphStore()
    )

    current_request = repo.get_current_request(experiment_id)
    request_id = request_version = request_content_hash = None
    input_artifact_hashes: list[str] = []
    if current_request is not None:
        request_id = current_request.request_id
        request_version = current_request.version
        request_content_hash = current_request.content_hash
        input_artifact_hashes = sorted(
            artifact.file_hash
            for artifact in repo.list_input_artifacts(current_request.request_id)
            if artifact.file_hash
        )

    manifest: dict[str, Any] = {
        "experiment_id": experiment_id,
        "snapshot_version": snapshot_version,
        "context": {
            "title": context.title,
            "disease": context.disease,
            "pathway": context.pathway,
            "organism": context.organism,
            "taxon_id": context.taxon_id,
            "assay": context.assay,
            "status": context.status.value,
            "current_request_id": context.current_request_id,
        },
        "counts": {
            "proteins": len(proteins),
            "peptides": len(peptides),
            "groups": len(groups),
            "annotations": len(annotations),
            "annotation_history": len(history),
            "differentials": len(differentials),
            "enrichments": len(enrichments),
        },
        "evidence_levels": {
            level.value: sum(1 for a in annotations if a.evidence_level is level)
            for level in EvidenceLevel
        },
        "annotations": [
            ann.model_dump(mode="json")
            for ann in sorted(annotations, key=lambda a: a.annotation_id)
        ],
        "annotation_history": [
            h.model_dump(mode="json")
            for h in sorted(history, key=lambda x: (x.changed_at, x.history_id))
        ],
        "differentials": [
            d.model_dump(mode="json")
            for d in sorted(differentials, key=lambda x: x.differential_id)
        ],
        "enrichments": [
            e.model_dump(mode="json")
            for e in sorted(enrichments, key=lambda x: (x.term_type, x.term))
        ],
        "graph": {
            key: graph_summary[key]
            for key in ("nodes", "edges", "nodes_by_label", "edges_by_type")
        },
        "versions": {
            "pipeline_version": pipeline_version,
            "model_version": model_version,
            "source_versions": source_versions,
            "query_and_params": query_and_params or {},
        },
        "request": {
            "request_id": request_id,
            "request_version": request_version,
            "request_content_hash": request_content_hash,
            "input_artifact_hashes": input_artifact_hashes,
        },
    }

    snapshot = ExperimentSnapshot(
        experiment_id=experiment_id,
        snapshot_version=snapshot_version,
        status=ExperimentStatus.FINAL,
        general_kg_version=source_versions,
        pipeline_version=pipeline_version,
        model_version=model_version,
        query_and_params=query_and_params or {},
        checksum=compute_manifest_checksum(manifest),
        report_artifact_ref=report_artifact_ref,
        request_id=request_id,
        request_version=request_version,
        request_content_hash=request_content_hash,
        input_artifact_hashes=input_artifact_hashes,
        manifest=manifest,
    )
    repo.save_snapshot(snapshot)  # 版本重复 → RequestVersionConflict（阻止覆盖）
    if supersede_prior:
        repo.supersede_other_snapshots(experiment_id, keep_snapshot_id=snapshot.snapshot_id)
    return snapshot


__all__ = [
    "FreezePreconditionError",
    "compute_manifest_checksum",
    "freeze_experiment",
    "verify_snapshot_integrity",
]
