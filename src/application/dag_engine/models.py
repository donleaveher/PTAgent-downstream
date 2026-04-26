"""
application.dag_engine.models：DAG 编译与调度相关的领域模型。

包含：
  - StepDependency：拓扑批次分析
  - ExecutionResults：步骤执行结果汇总
  - StepResult：单个步骤的执行结果
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# =============================================================================
# 枚举
# =============================================================================

class StepStatus(str, Enum):
    PENDING  = "pending"
    QUEUED   = "queued"
    RUNNING  = "running"
    SUCCESS  = "success"
    FAILED   = "failed"
    SKIPPED  = "skipped"


class StepMode(str, Enum):
    SEQUENTIAL = "sequential"
    PARALLEL   = "parallel"


# =============================================================================
# StepDependency — 拓扑排序 & 批次划分
# =============================================================================

@dataclass
class StepDependency:
    """
    工作流步骤依赖分析器。

    根据 step.depends_on 构建有向无环图（DAG），
    返回拓扑批次列表：同批次内可并行，批次间必须串行。
    """
    steps: dict[str, dict[str, Any]] = field(default_factory=dict)
    adj: dict[str, list[str]] = field(default_factory=dict)
    in_degree: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_steps(cls, steps: list[dict[str, Any]]) -> "StepDependency":
        """
        从 WorkflowStep list 构建依赖图。

        Args:
            steps: WorkflowStep.model_dump() 的列表

        Raises:
            ValueError: 检测到环（cycle）
        """
        dep = cls()
        dep.steps = {s["step_id"]: s for s in steps}
        dep.adj = {s["step_id"]: [] for s in steps}
        dep.in_degree = {s["step_id"]: len(s.get("depends_on", [])) for s in steps}

        # 构建反向邻接表（依赖 → 被依赖者）
        for s in steps:
            for dep_id in s.get("depends_on", []):
                if dep_id not in dep.adj:
                    raise ValueError(f"Unknown dependency step_id: {dep_id}")
                dep.adj[dep_id].append(s["step_id"])

        return dep

    def batches(self) -> list[list[str]]:
        """
        Kahn 算法拓扑排序 + 批次划分。

        Returns:
            list of step_id batches.
            批次 0 的所有步骤无依赖，可立即并行执行；
            批次 N 需等批次 N-1 全部完成。
        """
        in_deg = dict(self.in_degree)
        batches: list[list[str]] = []
        remaining = set(self.steps.keys())

        while remaining:
            # 取所有入度为 0 的节点（无未完成依赖）
            batch = sorted([sid for sid in remaining if in_deg[sid] == 0])
            if not batch:
                raise ValueError(
                    f"Cycle detected in workflow. Remaining steps: {remaining}"
                )
            batches.append(batch)
            # 模拟执行：这些步骤完成，移除它们对其他节点的贡献
            for sid in batch:
                remaining.remove(sid)
                for nb in self.adj.get(sid, []):
                    in_deg[nb] -= 1

        return batches

    def max_parallelism(self) -> int:
        """批次中最大并发数（用于展示）。"""
        return max((len(b) for b in self.batches()), default=0)

    def total_batches(self) -> int:
        return len(self.batches())


# =============================================================================
# StepResult — 单个步骤结果
# =============================================================================

@dataclass
class StepResult:
    """单个工作流步骤的执行结果。"""
    step_id: str
    tool_name: str
    status: StepStatus = StepStatus.PENDING
    run_id: str | None = None
    output_object_ids: list[str] = field(default_factory=list)
    output_summary: str = ""
    error_message: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "tool_name": self.tool_name,
            "status": self.status.value,
            "run_id": self.run_id,
            "output_object_ids": self.output_object_ids,
            "output_summary": self.output_summary,
            "error_message": self.error_message,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
        }


# =============================================================================
# ExecutionResults — 执行结果汇总
# =============================================================================

@dataclass
class ExecutionResults:
    """一组步骤的总体执行结果。"""
    steps: dict[str, StepResult] = field(default_factory=dict)
    total_duration_seconds: float = 0.0

    def get_by_status(self, status: StepStatus) -> list[StepResult]:
        return [r for r in self.steps.values() if r.status == status]

    def has_failures(self) -> bool:
        return any(r.status == StepStatus.FAILED for r in self.steps.values())

    def successful_count(self) -> int:
        return sum(1 for r in self.steps.values() if r.status == StepStatus.SUCCESS)

    def total_count(self) -> int:
        return len(self.steps)

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": {sid: r.to_dict() for sid, r in self.steps.items()},
            "total_duration_seconds": self.total_duration_seconds,
            "summary": {
                "total": self.total_count(),
                "success": self.successful_count(),
                "failed": len(self.get_by_status(StepStatus.FAILED)),
            },
        }
