"""
application.pipeline.graph：LangGraph 主图构建与条件边。

图结构：
  ingest_context
       │
       ▼
  plan_workflow
       │
       ▼
  human_approval ────── (condition) ────► execute_dag
       │                         ▲
       │  modify                 │ approved
       ▼                         │
  plan_workflow (重新规划)        │
       │
       │ reject                  │
       ▼                         │
    __end__◄──────────────────────┘

  execute_dag ──► distill_and_research ──► generate_report ──► __end__
"""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, StateGraph

from application.pipeline.nodes import (
    distill_and_research_node,
    execute_dag_node,
    generate_report_node,
    human_approval_node,
    ingest_context_node,
    plan_workflow_node,
)
from application.pipeline.state import PipelineState

logger = logging.getLogger(__name__)


def should_proceed(state: PipelineState) -> Literal[
    "execute_dag",
    "plan_workflow",
    "__end__",
]:
    """
    条件边路由 — human_approval 分流。

    Returns:
        "execute_dag"     — 用户 approve，进入无人值守执行
        "plan_workflow"  — 用户 modify，打回重新规划
        "__end__"        — 用户 reject 或其他异常，终止
    """
    action = state.get("human_action")
    session_id = state.get("session_id", "unknown")

    if action == "approve":
        logger.info("[graph] session=%s | routing → execute_dag (approved)", session_id)
        return "execute_dag"
    elif action == "modify":
        logger.info("[graph] session=%s | routing → plan_workflow (modify)", session_id)
        return "plan_workflow"
    else:
        logger.info(
            "[graph] session=%s | routing → __end__ (action=%s)",
            session_id,
            action,
        )
        return END


def build_pipeline_graph() -> StateGraph:
    """
    构建并返回编译后的 LangGraph。

    Returns:
        StateGraph.compile() 结果，可直接用于 graph.invoke() / graph.get_state().
    """
    builder = StateGraph(PipelineState)

    # ---- Node 注册 ----
    builder.add_node("ingest_context",       ingest_context_node)
    builder.add_node("plan_workflow",         plan_workflow_node)
    builder.add_node("human_approval",         human_approval_node)
    builder.add_node("execute_dag",            execute_dag_node)
    builder.add_node("distill_and_research",   distill_and_research_node)
    builder.add_node("generate_report",        generate_report_node)

    # ---- 入口 ----
    builder.set_entry_point("ingest_context")

    # ---- 主线顺序边 ----
    builder.add_edge("ingest_context",  "plan_workflow")
    builder.add_edge("plan_workflow",    "human_approval")

    # ---- 条件边：human_approval ──→ 分流 ----
    builder.add_conditional_edges(
        "human_approval",
        should_proceed,
        {
            "execute_dag":    "execute_dag",
            "plan_workflow":  "plan_workflow",
            END:              END,
        },
    )

    # ---- 执行后汇入 ----
    builder.add_edge("execute_dag",           "distill_and_research")
    builder.add_edge("distill_and_research", "generate_report")
    builder.add_edge("generate_report",      END)

    logger.info("[graph] Pipeline graph built successfully")
    return builder.compile()
