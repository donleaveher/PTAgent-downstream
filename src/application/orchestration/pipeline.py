"""下游知识管线编排（§11.2）。

把已落地的下游服务按依赖序串成端到端流程：

    import → base_annotation → ctd_disease → differential → enrichment
          → hypothesis → kg_projection → deep_search → freeze → report

特性：
- **独立状态**：用本模块的 `StepResult`/`PipelineResult`，不复用旧上游 `ExecutionResults`。
- **失败隔离**：每步独立 try/except，记录状态；`stop_on_error` 控制遇错是否中止。
- **幂等重跑 / 断点恢复**：各底层服务以稳定 ID upsert；freeze 若版本已存在则跳过；
  `steps=` 可只跑子集（从断点续跑）。
- **状态查询**：`pipeline_status` 从仓库派生当前进度。

外部源（UniProt MCP / CTD / Foldseek / 文献检索 / Neo4j）通过 config 注入；离线可注入
假源跑完整端到端，真实运行注入活实例。本管线替代旧 Mock LangGraph 主图（§13）。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from application.analysis import analyze_experiment_differential, run_disease_enrichment
from application.experiment.freeze import freeze_experiment
from application.graph.project_kg import project_experiment_kg
from application.knowledge import (
    annotate_experiment_diseases,
    enrich_experiment_proteins,
    generate_experiment_hypotheses,
    verify_experiment_hypotheses,
)
from application.report import ExperimentReport, generate_experiment_report
from pkg.experiment import (
    EvidenceLevel,
    ExperimentBundle,
    ExperimentRepository,
    get_experiment_store,
    ingest_experiment_bundle,
)


class StepStatus(str, Enum):
    OK = "ok"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class StepResult:
    name: str
    status: StepStatus
    summary: dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass(frozen=True)
class StepOutcome:
    """单步执行结果：状态 + 可选的报告对象（report 步产出）。"""

    result: StepResult
    report: "ExperimentReport | None" = None


@dataclass(frozen=True)
class PipelineResult:
    experiment_id: str
    steps: tuple[StepResult, ...]
    completed: bool                 # 选定步骤全部未失败
    failed_step: str | None
    snapshot_version: str | None
    report: ExperimentReport | None
    audit_log: tuple[str, ...] = ()  # LangGraph 编排逐步留痕；纯线性 runner 留空

    def step_statuses(self) -> dict[str, str]:
        return {s.name: s.status.value for s in self.steps}


@dataclass
class DownstreamPipelineConfig:
    """编排参数 + 可注入外部源（None → 走各服务的默认工厂，即真实实例）。"""

    snapshot_version: str = "1.0"
    pipeline_version: str = "ptagent-downstream-v3"
    model_version: str | None = None
    # 分析参数
    log2fc_threshold: float = 1.0
    q_threshold: float = 0.05
    min_samples: int = 2
    enrichment_min_overlap: int = 2
    top_k: int | None = None
    allow_unresolved_hypotheses: bool = False
    # 输入（import 步用；None 表示已预先导入）
    bundle: ExperimentBundle | None = None
    # 可注入外部源
    annotation_source: Any = None
    disease_source: Any = None
    structure_provider: Any = None
    gene_resolver: Any = None
    literature_source: Any = None
    graph_store: Any = None
    structural_neighbors: Sequence[Any] = ()


# ---------------- 各步骤（均 (experiment_id, repo, cfg) -> dict | ExperimentReport）----------------
def _step_import(experiment_id: str, repo: ExperimentRepository, cfg: DownstreamPipelineConfig):
    if cfg.bundle is None:
        return {"skipped": True, "reason": "no bundle provided; assuming already ingested"}
    if cfg.bundle.context.experiment_id != experiment_id:
        raise ValueError("bundle experiment_id does not match pipeline experiment_id")
    ingest_experiment_bundle(cfg.bundle, repo)
    return {
        "proteins": len(cfg.bundle.proteins),
        "groups": len(cfg.bundle.groups),
        "peptides": len(cfg.bundle.peptides),
    }


def _step_base_annotation(experiment_id, repo, cfg):
    return enrich_experiment_proteins(
        experiment_id, repository=repo, source=cfg.annotation_source
    )


def _step_ctd_disease(experiment_id, repo, cfg):
    return annotate_experiment_diseases(
        experiment_id, repository=repo, source=cfg.disease_source
    )


def _step_differential(experiment_id, repo, cfg):
    return analyze_experiment_differential(
        experiment_id,
        repository=repo,
        log2fc_threshold=cfg.log2fc_threshold,
        q_threshold=cfg.q_threshold,
        min_samples=cfg.min_samples,
    )


def _step_enrichment(experiment_id, repo, cfg):
    return run_disease_enrichment(
        experiment_id,
        repository=repo,
        q_threshold=cfg.q_threshold,
        min_overlap=cfg.enrichment_min_overlap,
    )


def _step_hypothesis(experiment_id, repo, cfg):
    return generate_experiment_hypotheses(
        experiment_id,
        repository=repo,
        structure_provider=cfg.structure_provider,
        gene_resolver=cfg.gene_resolver,
        disease_source=cfg.disease_source,
        top_k=cfg.top_k,
    )


def _step_kg_projection(experiment_id, repo, cfg):
    return project_experiment_kg(
        experiment_id,
        repository=repo,
        store=cfg.graph_store,
        structural_neighbors=cfg.structural_neighbors,
    )


def _step_deep_search(experiment_id, repo, cfg):
    return verify_experiment_hypotheses(
        experiment_id, repository=repo, source=cfg.literature_source
    )


def _step_freeze(experiment_id, repo, cfg):
    existing = [
        s for s in repo.list_snapshots(experiment_id)
        if s.snapshot_version == cfg.snapshot_version
    ]
    if existing:  # 幂等：版本已冻结则跳过，便于断点重跑
        return {"skipped": True, "reason": "snapshot version already frozen",
                "snapshot_version": cfg.snapshot_version}
    snapshot = freeze_experiment(
        experiment_id,
        snapshot_version=cfg.snapshot_version,
        pipeline_version=cfg.pipeline_version,
        repository=repo,
        model_version=cfg.model_version,
        allow_unresolved_hypotheses=cfg.allow_unresolved_hypotheses,
    )
    return {
        "snapshot_id": snapshot.snapshot_id,
        "snapshot_version": snapshot.snapshot_version,
        "checksum": snapshot.checksum,
    }


def _step_report(experiment_id, repo, cfg):
    return generate_experiment_report(experiment_id, cfg.snapshot_version, repository=repo)


_StepFn = Callable[[str, ExperimentRepository, DownstreamPipelineConfig], Any]

STEP_ORDER: tuple[str, ...] = (
    "import",
    "base_annotation",
    "ctd_disease",
    "differential",
    "enrichment",
    "hypothesis",
    "kg_projection",
    "deep_search",
    "freeze",
    "report",
)

_REGISTRY: dict[str, _StepFn] = {
    "import": _step_import,
    "base_annotation": _step_base_annotation,
    "ctd_disease": _step_ctd_disease,
    "differential": _step_differential,
    "enrichment": _step_enrichment,
    "hypothesis": _step_hypothesis,
    "kg_projection": _step_kg_projection,
    "deep_search": _step_deep_search,
    "freeze": _step_freeze,
    "report": _step_report,
}


def execute_step(
    name: str,
    experiment_id: str,
    repo: ExperimentRepository,
    cfg: DownstreamPipelineConfig,
) -> StepOutcome:
    """执行单个已注册步骤，归一为 ``StepOutcome``（含失败隔离 + 报告捕获）。

    纯线性 runner 与 LangGraph 节点共用此函数，业务逻辑不重复。
    """
    if name not in _REGISTRY:
        raise ValueError(f"unknown pipeline step: {name}")
    try:
        out = _REGISTRY[name](experiment_id, repo, cfg)
    except Exception as exc:  # 失败隔离：转成 FAILED，不抛出
        return StepOutcome(
            StepResult(name=name, status=StepStatus.FAILED, error=f"{type(exc).__name__}: {exc}")
        )
    if isinstance(out, ExperimentReport):
        return StepOutcome(
            StepResult(
                name=name,
                status=StepStatus.OK,
                summary={
                    "snapshot_version": out.snapshot_version,
                    "checksum": out.checksum,
                    "sections": list(out.sections),
                },
            ),
            report=out,
        )
    summary = out or {}
    status = StepStatus.SKIPPED if summary.get("skipped") else StepStatus.OK
    return StepOutcome(StepResult(name=name, status=status, summary=summary))


def run_downstream_pipeline(
    experiment_id: str,
    *,
    repository: ExperimentRepository | None = None,
    config: DownstreamPipelineConfig | None = None,
    steps: Sequence[str] | None = None,
    stop_on_error: bool = True,
) -> PipelineResult:
    """按依赖序运行下游知识管线；返回逐步状态与最终报告。"""

    repo = repository or get_experiment_store()
    cfg = config or DownstreamPipelineConfig()

    if repo.get_context(experiment_id) is None and (cfg.bundle is None):
        raise ValueError(f"unknown experiment_id: {experiment_id}")

    selected = set(steps) if steps is not None else set(STEP_ORDER)
    unknown = selected - set(STEP_ORDER)
    if unknown:
        raise ValueError(f"unknown pipeline steps: {sorted(unknown)}")
    ordered = [name for name in STEP_ORDER if name in selected]

    results: list[StepResult] = []
    report: ExperimentReport | None = None
    failed: str | None = None

    for name in ordered:
        outcome = execute_step(name, experiment_id, repo, cfg)
        results.append(outcome.result)
        if outcome.report is not None:
            report = outcome.report
        if outcome.result.status is StepStatus.FAILED:
            failed = name
            if stop_on_error:
                break

    return PipelineResult(
        experiment_id=experiment_id,
        steps=tuple(results),
        completed=failed is None,
        failed_step=failed,
        snapshot_version=cfg.snapshot_version,
        report=report,
    )


def pipeline_status(
    experiment_id: str, *, repository: ExperimentRepository | None = None
) -> dict[str, Any]:
    """从仓库派生当前管线进度（状态查询）。"""

    repo = repository or get_experiment_store()
    if repo.get_context(experiment_id) is None:
        raise ValueError(f"unknown experiment_id: {experiment_id}")

    annotations = repo.list_annotations(experiment_id)
    levels = {level: 0 for level in EvidenceLevel}
    for ann in annotations:
        levels[ann.evidence_level] += 1

    return {
        "experiment_id": experiment_id,
        "proteins": len(repo.list_proteins(experiment_id)),
        "annotations": len(annotations),
        "conclusions": levels[EvidenceLevel.CONCLUSION],
        "hypotheses": levels[EvidenceLevel.HYPOTHESIS],
        "refuted": levels[EvidenceLevel.REFUTED],
        "differentials": len(repo.list_differentials(experiment_id)),
        "enrichments": len(repo.list_enrichments(experiment_id)),
        "annotation_history": len(repo.list_annotation_history(experiment_id)),
        "snapshots": [s.snapshot_version for s in repo.list_snapshots(experiment_id)],
    }


__all__ = [
    "DownstreamPipelineConfig",
    "PipelineResult",
    "STEP_ORDER",
    "StepOutcome",
    "StepResult",
    "StepStatus",
    "execute_step",
    "pipeline_status",
    "run_downstream_pipeline",
]
