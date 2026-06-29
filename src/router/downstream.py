"""下游知识层对外 HTTP API（§11.1）。

把已落地的下游服务（导入 / 注释 / 差异 / 富集 / 假说 / KG / deep-search / 冻结 / 报告 /
管线）暴露成 JSON 接口。端点只做入参绑定 + 调 application 服务（复杂逻辑不在此）。

外部依赖（事实库 / 图库 / 管线外部源）经 FastAPI ``Depends`` 注入：生产默认走
``get_experiment_store()`` / ``get_kg_store()``，离线测试用 ``dependency_overrides``
注入内存实现。鉴权 / 实验所有权 / 审计日志（§11.1 末项）暂未接入。
"""

from __future__ import annotations

import dataclasses
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError

from application.experiment.freeze import FreezePreconditionError, freeze_experiment
from application.analysis import compare_experiments
from application.experiment.quantification_ingest import (
    QuantificationIngestError,
    ingest_experiment_quantifications,
)
from application.orchestration import (
    DownstreamPipelineConfig,
    pipeline_status,
    run_downstream_pipeline,
)
from application.report import generate_experiment_report
from pkg.experiment import (
    EvidenceLevel,
    ExperimentRepository,
    RequestVersionConflict,
    get_experiment_store,
    ingest_experiment_payload,
)
from pkg.graph import GraphStore, get_kg_store

downstream_router = APIRouter(prefix="/ptagent/api", tags=["downstream"])


# ---------------- 可注入依赖（测试用 dependency_overrides 覆盖）----------------
def get_repository() -> ExperimentRepository:
    return get_experiment_store()


def get_graph_store() -> GraphStore:
    return get_kg_store()


def get_pipeline_config() -> DownstreamPipelineConfig:
    return DownstreamPipelineConfig()


def _require(repo: ExperimentRepository, experiment_id: str) -> None:
    if repo.get_context(experiment_id) is None:
        raise HTTPException(404, f"unknown experiment_id: {experiment_id}")


def _validation_error_detail(exc: ValidationError, *, error: str) -> dict[str, Any]:
    """把 Pydantic 校验错误（含字段错与跨表引用错）包装成可定位、可修复的结构化报告。"""
    errors = [
        {
            "location": ".".join(str(p) for p in err["loc"]) or "(root)",
            "message": err["msg"],
            "type": err["type"],
        }
        for err in exc.errors()
    ]
    return {
        "error": error,
        "error_count": len(errors),
        "errors": errors,
        "hint": "字段规范与跨表引用规则见 docs/INPUT-CONTRACT.md",
    }


# ---------------- Body 模型 ----------------
class PipelineRunBody(BaseModel):
    snapshot_version: str | None = None
    steps: list[str] | None = None
    stop_on_error: bool = True


class FreezeBody(BaseModel):
    snapshot_version: str
    pipeline_version: str = "ptagent-downstream-v3"
    model_version: str | None = None
    allow_unresolved_hypotheses: bool = False


class QuantificationRowBody(BaseModel):
    """单行蛋白定量（下游自定义契约 §6）；experiment_id 由 URL 路径给出。"""
    protein_id: str = Field(min_length=1)
    group_id: str = Field(min_length=1)
    sample_id: str = Field(min_length=1)
    abundance: float
    meta: dict[str, Any] = Field(default_factory=dict)


class QuantificationsBody(BaseModel):
    quantifications: list[QuantificationRowBody]


# ---------------- 健康检查 ----------------
@downstream_router.get("/health")
def api_health() -> dict[str, Any]:
    return {"ok": True, "service": "ptagent-downstream"}


# ---------------- 实验：创建 / 状态 ----------------
@downstream_router.post("/experiments")
def api_create_experiment(
    payload: dict[str, Any], repo: ExperimentRepository = Depends(get_repository)
) -> dict[str, Any]:
    """校验并持久化输入三件套；校验失败 → 422。"""
    try:
        bundle = ingest_experiment_payload(payload, repo)
    except ValidationError as exc:
        raise HTTPException(
            422, detail=_validation_error_detail(exc, error="invalid experiment bundle")
        ) from exc
    return {
        "experiment_id": bundle.context.experiment_id,
        "proteins": len(bundle.proteins),
        "groups": len(bundle.groups),
        "peptides": len(bundle.peptides),
    }


# 注意：本路由必须在 `/experiments/{experiment_id}` 之前注册，否则 "compare" 会被
# 当作 experiment_id 捕获。
@downstream_router.get("/experiments/compare")
def api_compare_experiments(
    ids: str = Query(..., description="逗号分隔的 experiment_id（≥2 个）"),
    repo: ExperimentRepository = Depends(get_repository),
) -> dict[str, Any]:
    """跨实验比较差异蛋白（按 accession）与疾病结论（按 disease_id）。"""
    experiment_ids = [s for s in (x.strip() for x in ids.split(",")) if s]
    try:
        return compare_experiments(experiment_ids, repository=repo)
    except ValueError as exc:
        msg = str(exc)
        raise HTTPException(404 if "unknown experiment" in msg else 400, msg) from exc


@downstream_router.get("/experiments/{experiment_id}")
def api_get_experiment(
    experiment_id: str, repo: ExperimentRepository = Depends(get_repository)
) -> dict[str, Any]:
    _require(repo, experiment_id)
    return pipeline_status(experiment_id, repository=repo)


# ---------------- 定量：录入 / 查询（差异分析输入，下游自定义契约 §6）----------------
@downstream_router.post("/experiments/{experiment_id}/quantifications")
def api_ingest_quantifications(
    experiment_id: str,
    body: QuantificationsBody,
    repo: ExperimentRepository = Depends(get_repository),
) -> dict[str, Any]:
    """录入一批 {protein_id, group_id, sample_id, abundance}。

    引用了该实验不存在的 protein_id / group_id → 整批拒绝 422。
    同一 (protein, group, sample) 重复提交按 upsert 覆盖。
    """
    _require(repo, experiment_id)
    try:
        return ingest_experiment_quantifications(
            experiment_id,
            [row.model_dump() for row in body.quantifications],
            repository=repo,
        )
    except QuantificationIngestError as exc:
        raise HTTPException(422, str(exc)) from exc


@downstream_router.get("/experiments/{experiment_id}/quantifications")
def api_list_quantifications(
    experiment_id: str, repo: ExperimentRepository = Depends(get_repository)
) -> dict[str, Any]:
    _require(repo, experiment_id)
    rows = repo.list_quantifications(experiment_id)
    return {
        "experiment_id": experiment_id,
        "count": len(rows),
        "quantifications": [r.model_dump(mode="json") for r in rows],
    }


# ---------------- 查询：注释 / 差异 / 富集 / 历史 ----------------
@downstream_router.get("/experiments/{experiment_id}/annotations")
def api_list_annotations(
    experiment_id: str,
    evidence_level: str | None = Query(None, description="CONCLUSION/HYPOTHESIS/REFUTED"),
    repo: ExperimentRepository = Depends(get_repository),
) -> dict[str, Any]:
    _require(repo, experiment_id)
    rows = repo.list_annotations(experiment_id)
    if evidence_level:
        try:
            level = EvidenceLevel(evidence_level)
        except ValueError as exc:
            raise HTTPException(400, f"invalid evidence_level: {evidence_level}") from exc
        rows = [r for r in rows if r.evidence_level is level]
    return {
        "experiment_id": experiment_id,
        "count": len(rows),
        "annotations": [r.model_dump(mode="json") for r in rows],
    }


@downstream_router.get("/experiments/{experiment_id}/differentials")
def api_list_differentials(
    experiment_id: str,
    only_significant: bool = Query(False),
    repo: ExperimentRepository = Depends(get_repository),
) -> dict[str, Any]:
    _require(repo, experiment_id)
    rows = repo.list_differentials(experiment_id)
    if only_significant:
        rows = [r for r in rows if r.is_differential]
    return {
        "experiment_id": experiment_id,
        "count": len(rows),
        "differentials": [r.model_dump(mode="json") for r in rows],
    }


@downstream_router.get("/experiments/{experiment_id}/enrichments")
def api_list_enrichments(
    experiment_id: str, repo: ExperimentRepository = Depends(get_repository)
) -> dict[str, Any]:
    _require(repo, experiment_id)
    rows = repo.list_enrichments(experiment_id)
    return {
        "experiment_id": experiment_id,
        "count": len(rows),
        "enrichments": [r.model_dump(mode="json") for r in rows],
    }


@downstream_router.get("/experiments/{experiment_id}/history")
def api_list_history(
    experiment_id: str, repo: ExperimentRepository = Depends(get_repository)
) -> dict[str, Any]:
    _require(repo, experiment_id)
    rows = repo.list_annotation_history(experiment_id)
    return {
        "experiment_id": experiment_id,
        "count": len(rows),
        "history": [r.model_dump(mode="json") for r in rows],
    }


# ---------------- 本次实验 KG：从蛋白展开证据路径 ----------------
@downstream_router.get("/experiments/{experiment_id}/kg/proteins/{accession}/diseases")
def api_protein_diseases(
    experiment_id: str,
    accession: str,
    repo: ExperimentRepository = Depends(get_repository),
    graph: GraphStore = Depends(get_graph_store),
) -> dict[str, Any]:
    _require(repo, experiment_id)
    links = graph.protein_diseases(accession, experiment_id=experiment_id)
    return {
        "experiment_id": experiment_id,
        "accession": accession,
        "diseases": [dataclasses.asdict(link) for link in links],
    }


# ---------------- 编排：运行下游管线 ----------------
@downstream_router.post("/experiments/{experiment_id}/pipeline")
def api_run_pipeline(
    experiment_id: str,
    body: PipelineRunBody,
    repo: ExperimentRepository = Depends(get_repository),
    config: DownstreamPipelineConfig = Depends(get_pipeline_config),
) -> dict[str, Any]:
    _require(repo, experiment_id)
    if body.snapshot_version:
        config.snapshot_version = body.snapshot_version
    try:
        result = run_downstream_pipeline(
            experiment_id,
            repository=repo,
            config=config,
            steps=body.steps,
            stop_on_error=body.stop_on_error,
        )
    except ValueError as exc:  # 未知步骤等
        raise HTTPException(400, str(exc)) from exc
    return {
        "experiment_id": experiment_id,
        "completed": result.completed,
        "failed_step": result.failed_step,
        "snapshot_version": result.snapshot_version,
        "steps": result.step_statuses(),
        "report_checksum": result.report.checksum if result.report else None,
    }


# ---------------- 冻结 / 快照 / 报告 ----------------
@downstream_router.post("/experiments/{experiment_id}/freeze")
def api_freeze(
    experiment_id: str,
    body: FreezeBody,
    repo: ExperimentRepository = Depends(get_repository),
) -> dict[str, Any]:
    _require(repo, experiment_id)
    try:
        snapshot = freeze_experiment(
            experiment_id,
            snapshot_version=body.snapshot_version,
            pipeline_version=body.pipeline_version,
            repository=repo,
            model_version=body.model_version,
            allow_unresolved_hypotheses=body.allow_unresolved_hypotheses,
        )
    except (FreezePreconditionError, RequestVersionConflict) as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_version": snapshot.snapshot_version,
        "status": snapshot.status.value,
        "checksum": snapshot.checksum,
    }


@downstream_router.get("/experiments/{experiment_id}/snapshots")
def api_list_snapshots(
    experiment_id: str, repo: ExperimentRepository = Depends(get_repository)
) -> dict[str, Any]:
    _require(repo, experiment_id)
    snapshots = repo.list_snapshots(experiment_id)
    return {
        "experiment_id": experiment_id,
        "snapshots": [
            {
                "snapshot_id": s.snapshot_id,
                "snapshot_version": s.snapshot_version,
                "status": s.status.value,
                "checksum": s.checksum,
                "frozen_at": s.frozen_at.isoformat(),
            }
            for s in snapshots
        ],
    }


@downstream_router.get("/experiments/{experiment_id}/reports")
def api_list_reports(
    experiment_id: str, repo: ExperimentRepository = Depends(get_repository)
) -> dict[str, Any]:
    """列出已落库的报告 artifact（元数据，不含正文）。"""
    _require(repo, experiment_id)
    reports = repo.list_reports(experiment_id)
    return {
        "experiment_id": experiment_id,
        "count": len(reports),
        "reports": [
            {
                "report_id": r.report_id,
                "snapshot_id": r.snapshot_id,
                "snapshot_version": r.snapshot_version,
                "report_format": r.report_format,
                "checksum": r.checksum,
                "sections": list(r.sections),
                "generated_at": r.generated_at.isoformat(),
            }
            for r in reports
        ],
    }


@downstream_router.get("/experiments/{experiment_id}/report")
def api_report(
    experiment_id: str,
    snapshot_version: str = Query(..., description="冻结快照版本，如 1.0"),
    repo: ExperimentRepository = Depends(get_repository),
) -> dict[str, Any]:
    _require(repo, experiment_id)
    stored = repo.get_report(experiment_id, snapshot_version)
    if stored is not None:  # 优先返回已落库 artifact（稳定、带 generated_at）
        return {
            "experiment_id": experiment_id,
            "snapshot_version": stored.snapshot_version,
            "checksum": stored.checksum,
            "sections": list(stored.sections),
            "markdown": stored.content,
            "report_id": stored.report_id,
            "generated_at": stored.generated_at.isoformat(),
            "persisted": True,
        }
    try:  # 快照在但报告步未跑过 → 按需只读生成（不落库）
        report = generate_experiment_report(experiment_id, snapshot_version, repository=repo)
    except ValueError as exc:
        msg = str(exc)
        raise HTTPException(409 if "integrity" in msg else 404, msg) from exc
    return {
        "experiment_id": experiment_id,
        "snapshot_version": report.snapshot_version,
        "checksum": report.checksum,
        "sections": list(report.sections),
        "markdown": report.markdown,
        "persisted": False,
    }


__all__ = [
    "downstream_router",
    "get_graph_store",
    "get_pipeline_config",
    "get_repository",
]
