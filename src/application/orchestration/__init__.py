"""下游知识管线编排（新版，替代旧 Mock LangGraph 主图）。

- 纯 Python 线性 runner：:func:`run_downstream_pipeline`（含失败隔离/幂等/子集/状态查询）。
- LangGraph 主图（旧风格新实现）：:func:`run_downstream_graph` / :func:`build_downstream_graph`
  （StateGraph + 共享状态 + 冻结前人审批条件边 + audit log），节点复用同一批步骤实现。
"""

from application.orchestration.graph import (
    DownstreamState,
    build_downstream_graph,
    run_downstream_graph,
)
from application.orchestration.pipeline import (
    STEP_ORDER,
    DownstreamPipelineConfig,
    PipelineResult,
    StepOutcome,
    StepResult,
    StepStatus,
    execute_step,
    pipeline_status,
    run_downstream_pipeline,
)

__all__ = [
    "DownstreamPipelineConfig",
    "DownstreamState",
    "PipelineResult",
    "STEP_ORDER",
    "StepOutcome",
    "StepResult",
    "StepStatus",
    "build_downstream_graph",
    "execute_step",
    "pipeline_status",
    "run_downstream_graph",
    "run_downstream_pipeline",
]
