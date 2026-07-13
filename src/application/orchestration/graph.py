"""下游知识管线的 LangGraph 编排（§11.2，旧主图风格的新实现）。

沿用旧 `application.pipeline` 的**结构风格**（StateGraph + 共享状态 + 条件边 + audit
log），但节点语义换成**真实下游服务**、状态是**新定义**（非旧 `ExecutionResults`）、无 Mock：

    import → base_annotation → ctd_disease → differential → enrichment
          → neighbor_search → hypothesis → deep_search → kg_projection
          → human_approval
            ─approve→ freeze → report → END
            ─modify─→ END   （打回，人改后重跑）
            ─reject─→ END

节点复用 :func:`application.orchestration.pipeline.execute_step`（业务逻辑不重复）。
失败隔离：任一步失败后下游节点 no-op 跳过，条件边收敛到 END。

注：当前为内存 ``invoke``（state 携带 repo/config 等活对象，未接 checkpointer）；接
LangGraph checkpointer + ``interrupt_before=["human_approval"]`` 即得真正的暂停/恢复式
人在回路（人给出 approve/modify/reject 后再恢复）。
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph

from application.orchestration.pipeline import (
    DownstreamPipelineConfig,
    PipelineResult,
    StepResult,
    StepStatus,
    execute_step,
)
from application.report import ExperimentReport
from pkg.experiment import ExperimentRepository, get_experiment_store

_HUMAN_ACTIONS = ("approve", "modify", "reject")
# deep_search 与 freeze 之间插入 human_approval；两侧均按依赖序线性
_PRE_GATE = (
    "import",
    "base_annotation",
    "ctd_disease",
    "differential",
    "enrichment",
    "neighbor_search",
    "hypothesis",
    "deep_search",
    "kg_projection",
)
_POST_GATE = ("freeze", "report")


class DownstreamState(TypedDict, total=False):
    """LangGraph 共享状态（下游专用，非旧 ExecutionResults）。"""

    experiment_id: str
    repo: ExperimentRepository
    config: DownstreamPipelineConfig
    human_action: str
    steps: Annotated[list[StepResult], operator.add]   # 逐步累积
    audit_log: Annotated[list[str], operator.add]       # 逐步留痕
    failed_step: str | None
    report: ExperimentReport | None


def _make_node(name: str):
    def node(state: DownstreamState) -> dict[str, Any]:
        if state.get("failed_step"):  # 失败隔离：下游 no-op
            return {"audit_log": [f"{name}: skipped (upstream failure)"]}
        outcome = execute_step(name, state["experiment_id"], state["repo"], state["config"])
        update: dict[str, Any] = {
            "steps": [outcome.result],
            "audit_log": [f"{name}: {outcome.result.status.value}"],
        }
        if outcome.result.status is StepStatus.FAILED:
            update["failed_step"] = name
        if outcome.report is not None:
            update["report"] = outcome.report
        return update

    return node


def _human_approval(state: DownstreamState) -> dict[str, Any]:
    if state.get("failed_step"):
        return {"audit_log": ["human_approval: skipped (upstream failure)"]}
    action = state.get("human_action", "approve")
    return {"audit_log": [f"human_approval: {action}"]}


def _route_after_approval(state: DownstreamState) -> str:
    if state.get("failed_step"):
        return "reject"
    action = state.get("human_action", "approve")
    return action if action in _HUMAN_ACTIONS else "reject"


def build_downstream_graph():
    """构建并编译下游 LangGraph 主图。"""
    builder = StateGraph(DownstreamState)
    for name in (*_PRE_GATE, *_POST_GATE):
        builder.add_node(name, _make_node(name))
    builder.add_node("human_approval", _human_approval)

    builder.set_entry_point(_PRE_GATE[0])
    for upstream, downstream in zip(_PRE_GATE, _PRE_GATE[1:]):
        builder.add_edge(upstream, downstream)
    builder.add_edge(_PRE_GATE[-1], "human_approval")
    builder.add_conditional_edges(
        "human_approval",
        _route_after_approval,
        {"approve": "freeze", "modify": END, "reject": END},
    )
    builder.add_edge("freeze", "report")
    builder.add_edge("report", END)
    return builder.compile()


def run_downstream_graph(
    experiment_id: str,
    *,
    repository: ExperimentRepository | None = None,
    config: DownstreamPipelineConfig | None = None,
    human_action: str = "approve",
) -> PipelineResult:
    """跑下游 LangGraph 主图；``human_action`` 模拟人审批（approve/modify/reject）。

    ``completed`` = 无失败且走到 report（reject/modify 在冻结前停 → 非 completed）。
    """
    repo = repository or get_experiment_store()
    cfg = config or DownstreamPipelineConfig()
    if repo.get_context(experiment_id) is None and cfg.bundle is None:
        raise ValueError(f"unknown experiment_id: {experiment_id}")

    final = build_downstream_graph().invoke(
        {
            "experiment_id": experiment_id,
            "repo": repo,
            "config": cfg,
            "human_action": human_action,
            "steps": [],
            "audit_log": [],
        }
    )
    steps = tuple(final.get("steps", ()))
    failed = final.get("failed_step")
    report = final.get("report")
    return PipelineResult(
        experiment_id=experiment_id,
        steps=steps,
        completed=failed is None and report is not None,
        failed_step=failed,
        snapshot_version=cfg.snapshot_version,
        report=report,
        audit_log=tuple(final.get("audit_log", ())),
    )


__all__ = ["DownstreamState", "build_downstream_graph", "run_downstream_graph"]
