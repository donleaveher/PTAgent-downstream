"""
application.pipeline.state：LangGraph PipelineState TypedDict 定义。

与 HTTP DTO（model.http.pipeline）分离：
- TypedDict 用于 LangGraph 内部状态流；
- Pydantic Model 用于 HTTP 序列化。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from model.http.pipeline import (
        ExperimentContext,
        ExecutionResults,
        FinalReport,
        KeyFinding,
        PipelineStatus,
        ResearchEvidence,
        WorkflowPlan,
    )


class PipelineState(TypedDict, total=False):
    """
    LangGraph 共享状态。

    每个 Node 只读写自己关心的字段；非必需字段均 total=False。
    """

    # ---- 身份与生命周期 ----
    session_id: str
    pipeline_status: PipelineStatus

    # ---- 各 Node 的数据舱 ----
    experiment_context: ExperimentContext | None
    proposed_plan: WorkflowPlan | None
    execution_results: ExecutionResults | None
    key_findings: list[KeyFinding]
    research_evidence: list[ResearchEvidence]
    final_report: FinalReport | None

    # ---- 审计日志 ----
    audit_log: list[str]

    # ---- 人在回路状态 ----
    # human_approval Node 写入；条件边函数读取
    human_action: str | None  # "approve" | "modify" | "reject"
    rejection_reason: str | None

    # ---- DataObject 引用（Node 间传递）----
    # 局部命名 → DataObject ID
    data_refs: dict[str, str]

    # ---- 快照（用于断点恢复）----
    filter_config_snapshot: dict[str, Any] | None
    updated_at: str
