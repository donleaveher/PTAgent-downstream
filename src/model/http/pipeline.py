"""
model.http.pipeline：科研流（Pipeline）HTTP 请求/响应 Pydantic 模型。

与 FastAPI Router `pipeline_router` 一一对应；DataPlane 模型在 `pkg.data_plane`。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# =============================================================================
# 枚举
# =============================================================================

class PipelineStatus(str, Enum):
    IDLE              = "idle"
    RUNNING           = "running"
    WAITING_APPROVAL  = "waiting_approval"
    APPROVED          = "approved"
    REJECTED          = "rejected"
    COMPLETED         = "completed"
    FAILED            = "failed"


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


class HumanAction(str, Enum):
    APPROVE = "approve"
    MODIFY  = "modify"
    REJECT  = "reject"


# =============================================================================
# FilterConfig — 前置装填 HITL 核心
# =============================================================================

class FilterCriterion(BaseModel):
    """单条过滤规则。"""
    field: str = Field(..., description="结果对象的字段路径，如 'score'、'q_value'")
    operator: str = Field(
        ...,
        description="比较操作符: gt | gte | lt | lte | eq | in | top_n_percent",
    )
    value: Any = Field(..., description="比较值或列表（operator=in 时）")
    label: str = Field(default="", description="规则展示名，如 'P-value < 0.05'")


class FilterConfig(BaseModel):
    """
    人在回路·过滤策略配置。

    用户在启动前一次性设定，执行阶段不再干预。
    """
    enabled: bool = Field(default=True, description="是否启用过滤")

    # 按置信度 / 统计显著性的通用阈值
    confidence_threshold: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="置信度下限（如 0.9）"
    )
    top_n: int | None = Field(
        default=None,
        ge=1,
        description="保留 Top N 条结果（如 100）"
    )
    top_n_percent: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="保留 Top N% 结果（如 10.0）"
    )

    # 自定义过滤规则（支持多字段联合过滤）
    custom_rules: list[FilterCriterion] = Field(
        default_factory=list,
        description="用户自定义过滤规则列表"
    )

    # 保留策略：被过滤掉的数据是否仍保留元数据（可追溯）
    keep_rejected_metadata: bool = Field(
        default=True,
        description="被过滤的结果是否保留元数据记录"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "enabled": True,
                "confidence_threshold": 0.9,
                "top_n": 100,
                "top_n_percent": None,
                "custom_rules": [
                    {
                        "field": "q_value",
                        "operator": "lt",
                        "value": 0.05,
                        "label": "P-value < 0.05 (Benjamini-Hochberg)"
                    },
                    {
                        "field": "coverage_percent",
                        "operator": "gte",
                        "value": 80.0,
                        "label": "Coverage ≥ 80%"
                    }
                ],
                "keep_rejected_metadata": True
            }
        }


# =============================================================================
# WorkflowPresets — 工作流模板
# =============================================================================

class ToolPresetBinding(BaseModel):
    """工作流步骤与工具的绑定关系。"""
    step_id: str = Field(..., description="步骤 ID")
    tool_name: str = Field(..., description="MCP 工具名称")
    parameters: dict[str, Any] = Field(default_factory=dict)
    mode: StepMode = StepMode.SEQUENTIAL


class WorkflowPreset(BaseModel):
    """
    工作流预设模板。

    允许用户在前置阶段选择一个预定义的工具组合与连线方式，
    或完全交由 AI 自动生成（preset_key = "__auto__"）。
    """
    preset_key: str = Field(
        ...,
        description="预设标识；'__auto__' 表示完全由 AI 规划"
    )
    name: str = Field(default="", description="预设名称")
    description: str = Field(default="", description="预设说明")
    tool_bindings: list[ToolPresetBinding] = Field(default_factory=list)
    allow_tool_reorder: bool = Field(
        default=True,
        description="AI 是否可以重新排列/增删步骤"
    )


# =============================================================================
# Workflow Plan 结构（AI 生成，用户可修改）
# =============================================================================

class WorkflowStep(BaseModel):
    """工作流中的单个步骤。"""
    step_id: str = Field(..., description="唯一步骤 ID，格式: step_0, step_1 …")
    tool_name: str = Field(..., description="MCP 工具名称")
    tool_category: str = Field(default="", description="工具分类，如 'basic.peptide'")
    description: str = Field(default="", description="AI 对该步骤的描述")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="工具参数字典；DataObject 引用格式: {'$ref': 'dobj_xxx'}"
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="所依赖的 step_id 列表"
    )
    mode: StepMode = StepMode.SEQUENTIAL
    estimated_duration: str = Field(default="", description="AI 估算时长")
    filter_tag: str = Field(
        default="",
        description="该步骤结果在哪个 FilterCriterion 之后产生"
    )


class WorkflowPlan(BaseModel):
    """完整的工作流执行计划。"""
    plan_id: str = Field(default="", description="计划唯一 ID")
    title: str = Field(default="", description="计划标题")
    rationale: str = Field(
        default="",
        description="AI 生成该计划的总思路说明"
    )
    steps: list[WorkflowStep] = Field(
        ...,
        min_length=1,
        description="步骤列表；depends_on 构造 DAG"
    )
    estimated_total_time: str = Field(default="", description="总估算时长")
    metadata: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# 实验上下文（用户输入）
# =============================================================================

class ExperimentContext(BaseModel):
    """用户提交的实验上下文。"""
    session_id: str = Field(..., description="所属 session")
    title: str = Field(default="", description="实验标题")
    description: str = Field(default="", description="实验背景描述")
    hypothesis: str = Field(default="", description="科学假设/研究目标")
    data_object_ids: list[str] = Field(
        default_factory=list,
        description="引用的 DataObject ID 列表"
    )
    filter_config: FilterConfig = Field(
        default_factory=FilterConfig(),
        description="过滤策略（前置装填 HITL）"
    )
    workflow_preset: WorkflowPreset | None = Field(
        default=None,
        description="工作流预设模板（可选）"
    )
    constraints: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# 执行结果
# =============================================================================

class StepResult(BaseModel):
    """单个步骤的执行结果。"""
    step_id: str
    tool_name: str
    status: StepStatus
    run_id: Optional[str] = Field(default=None, description="底层 Run ID")
    output_object_ids: list[str] = Field(default_factory=list)
    output_summary: str = Field(default="", description="结果摘要")
    error_message: str = Field(default="")
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_seconds: float = 0.0


class ExecutionResults(BaseModel):
    """执行结果汇总。"""
    steps: dict[str, StepResult] = Field(default_factory=dict)
    total_duration_seconds: float = 0.0


# =============================================================================
# 中间结论与证据
# =============================================================================

class KeyFinding(BaseModel):
    """从执行结果中提炼的关键结论。"""
    finding_id: str
    topic: str = Field(..., description="结论主题")
    content: str = Field(..., description="具体结论内容")
    source_steps: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    evidence: list[str] = Field(default_factory=list)


class ResearchEvidence(BaseModel):
    """文献检索证据。"""
    query: str
    retrieved_chunks: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


# =============================================================================
# 最终报告
# =============================================================================

class ReportSection(BaseModel):
    """报告章节。"""
    level: int = Field(..., ge=1, le=6)
    heading: str = Field(...)
    content: str = Field(default="")


class FinalReport(BaseModel):
    """最终生成的研究报告。"""
    title: str = Field(default="")
    sections: list[ReportSection] = Field(default_factory=list)
    raw_markdown: str = Field(default="")
    attached_data_object_ids: list[str] = Field(default_factory=list)


# =============================================================================
# 持久化 State（SQLite 列映射）
# =============================================================================

class PipelineStateRecord(BaseModel):
    """存储到 dp_session 表 pipeline_state 列的 JSON。"""
    status: PipelineStatus
    proposed_plan: WorkflowPlan | None = None
    execution_results: ExecutionResults | None = None
    key_findings: list[KeyFinding] = Field(default_factory=list)
    research_evidence: list[ResearchEvidence] = Field(default_factory=list)
    final_report: FinalReport | None = None
    audit_log: list[str] = Field(default_factory=list)
    human_action: HumanAction | None = None
    rejection_reason: str | None = None
    data_refs: dict[str, str] = Field(default_factory=dict)
    filter_config_snapshot: FilterConfig | None = None
    updated_at: str = Field(default="")
