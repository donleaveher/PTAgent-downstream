"""
Node 2: plan_workflow

职责：
  - 调用 ToolGateway.list_tools() 动态获取所有已注册的 MCP 工具 Schema
  - 组装 LLM Prompt（空壳/Mock），生成 WorkflowPlan
  - 若用户提供 WorkflowPreset，优先使用 preset 的工具绑定
  - 记录审计日志

当前：空壳实现 + Mock 数据；后续接入 ToolLlmAgent 替换 _mock_generate_plan()。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from application.pipeline.state import PipelineState

if TYPE_CHECKING:
    from model.http.pipeline import WorkflowPlan

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 占位接口（后续替换为真实的 ToolGateway / LLM 调用）
# ---------------------------------------------------------------------------


def list_mcp_tools() -> list[dict[str, Any]]:
    """
    【占位】调用 ToolBroker.list_tools() 获取所有已注册工具。

    替换方式：
        from pkg.mcp.core.broker import ToolBroker
        broker: ToolBroker = ...  # 从 application context 注入
        return [t.model_dump() for t in broker.list_tools()]
    """
    # Mock 返回值，用于开发期跑通图
    return [
        {
            "name": "normalize_peptide",
            "description": "对肽段序列进行标准化处理（去修饰、格式统一）",
            "input_schema": {
                "type": "object",
                "properties": {
                    "peptide": {"type": "string", "description": "肽段序列"},
                    "charge": {"type": "integer", "default": 1},
                },
                "required": ["peptide"],
            },
            "tool_category": "basic.peptide",
            "tool_group": "basic.peptide",
        },
        {
            "name": "mass_search",
            "description": "在已知数据库中搜索质荷比 (m/z)",
            "input_schema": {
                "type": "object",
                "properties": {
                    "mz": {"type": "number", "description": "质荷比"},
                    "tolerance": {"type": "number", "default": 0.02},
                    "database": {"type": "string", "default": "uniprot"},
                },
                "required": ["mz"],
            },
            "tool_category": "basic.peptide",
            "tool_group": "basic.peptide",
        },
        {
            "name": "deepxiv_search",
            "description": "基于深度学习的文献检索（DeepXiv）",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
            "tool_category": "general.deepxiv",
            "tool_group": "general.deepxiv",
        },
        {
            "name": "uniprot_fasta_fetch",
            "description": "从 UniProt 获取 FASTA 序列",
            "input_schema": {
                "type": "object",
                "properties": {
                    "accession": {"type": "string"},
                    "reviewed_only": {"type": "boolean", "default": True},
                },
                "required": ["accession"],
            },
            "tool_category": "general.uniprot",
            "tool_group": "general.uniprot",
        },
    ]


def generate_workflow_plan(
    tools: list[dict[str, Any]],
    experiment_context: dict[str, Any],
    preset_steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    【占位】调用 LLM 生成 WorkflowPlan JSON。

    替换方式：
        llm_client = get_llm_client()   # 从 context 注入
        prompt = _build_plan_prompt(tools, experiment_context)
        response = llm_client.complete(prompt, json_schema=WorkflowPlanSchema)
        return response  # Pydantic-validated WorkflowPlan
    """
    return _mock_generate_plan(tools, experiment_context, preset_steps)


# ---------------------------------------------------------------------------
# Node 函数
# ---------------------------------------------------------------------------

def plan_workflow_node(state: PipelineState) -> dict[str, Any]:
    """
    LangGraph Node — plan_workflow

    工作流程：
      1. 动态发现 MCP 工具（list_mcp_tools）
      2. 若用户提供了 WorkflowPreset，使用 preset 工具绑定
      3. 调用 LLM 生成计划（当前为空壳/Mock）
      4. 写入 proposed_plan，进入 WAITING_APPROVAL 状态
    """
    session_id = state["session_id"]
    ctx = state.get("experiment_context")
    now = _ts()

    logger.info("[plan_workflow] session=%s | discovering MCP tools …", session_id)

    # ① 动态获取工具列表
    available_tools = list_mcp_tools()
    logger.info(
        "[plan_workflow] session=%s | found %d tools",
        session_id,
        len(available_tools),
    )

    # ② 获取用户预设
    preset_steps: list[dict[str, Any]] | None = None
    if ctx and ctx.workflow_preset and ctx.workflow_preset.preset_key != "__auto__":
        preset_steps = [b.model_dump() for b in ctx.workflow_preset.tool_bindings]
        logger.info(
            "[plan_workflow] session=%s | using preset '%s' with %d bindings",
            session_id,
            ctx.workflow_preset.preset_key,
            len(preset_steps),
        )

    # ③ 生成计划（Mock / LLM）
    plan_dict = generate_workflow_plan(
        tools=available_tools,
        experiment_context=ctx.model_dump() if ctx else {},
        preset_steps=preset_steps,
    )

    # ④ 校验 plan_id
    if not plan_dict.get("plan_id"):
        plan_dict["plan_id"] = f"plan_{uuid.uuid4().hex[:8]}"

    logger.info(
        "[plan_workflow] session=%s | plan_id=%s | steps=%d",
        session_id,
        plan_dict.get("plan_id"),
        len(plan_dict.get("steps", [])),
    )

    return {
        "proposed_plan": plan_dict,
        "pipeline_status": "waiting_approval",
        "audit_log": [
            f"[{now}][plan_workflow] MCP tools discovered: {[t['name'] for t in available_tools]}",
            f"[{now}][plan_workflow] Plan generated: {plan_dict.get('plan_id')}",
            f"[{now}][plan_workflow] Steps: {len(plan_dict.get('steps', []))}",
        ],
        "updated_at": now,
    }


# ---------------------------------------------------------------------------
# Mock 实现（开发期用）
# ---------------------------------------------------------------------------

def _mock_generate_plan(
    tools: list[dict[str, Any]],
    ctx: dict[str, Any],
    preset_steps: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """生成 Mock 计划（可替换为真实 LLM 调用）。"""
    if preset_steps:
        steps = [_preset_to_step(ps, i) for i, ps in enumerate(preset_steps)]
    else:
        steps = [
            {
                "step_id": "step_0",
                "tool_name": "normalize_peptide",
                "tool_category": "basic.peptide",
                "description": "对输入肽段进行标准化处理",
                "parameters": {
                    "peptide": {"$ref": "input_0"},
                    "charge": 2,
                },
                "depends_on": [],
                "mode": "sequential",
                "estimated_duration": "~30s",
            },
            {
                "step_id": "step_1",
                "tool_name": "mass_search",
                "tool_category": "basic.peptide",
                "description": "在 UniProt 数据库中搜索标准化后的质荷比",
                "parameters": {
                    "mz": 450.5,
                    "tolerance": 0.02,
                    "database": "uniprot",
                },
                "depends_on": ["step_0"],
                "mode": "sequential",
                "estimated_duration": "~2min",
            },
            {
                "step_id": "step_2",
                "tool_name": "deepxiv_search",
                "tool_category": "general.deepxiv",
                "description": "基于搜索结果检索相关文献",
                "parameters": {
                    "query": ctx.get("hypothesis", "mass spectrometry protein identification"),
                    "top_k": 5,
                },
                "depends_on": ["step_1"],
                "mode": "sequential",
                "estimated_duration": "~1min",
            },
        ]

    return {
        "plan_id": f"plan_{uuid.uuid4().hex[:8]}",
        "title": ctx.get("title", "Untitled Experiment"),
        "rationale": (
            f"基于假设「{ctx.get('hypothesis', 'N/A')}」构建以下三步工作流："
            "① 肽段标准化 → ② 质荷比数据库检索 → ③ 文献证据收集。"
        ),
        "steps": steps,
        "estimated_total_time": "~5min",
        "metadata": {"generated_by": "mock_llm", "model": "mock-v0.1"},
    }


def _preset_to_step(ps: dict[str, Any], idx: int) -> dict[str, Any]:
    from model.http.pipeline import StepMode
    return {
        "step_id": f"step_{idx}",
        "tool_name": ps.get("tool_name", ""),
        "tool_category": "",
        "description": f"Preset step {idx}",
        "parameters": ps.get("parameters", {}),
        "depends_on": [],
        "mode": ps.get("mode", StepMode.SEQUENTIAL.value),
        "estimated_duration": "",
    }


def _ts() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
