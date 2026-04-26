"""
Node 3: human_approval

职责：
  - 作为 LangGraph 的 interrupt 触发点
  - 检查 state["human_action"]：
      - None        → 写入 waiting_approval，LangGraph 自动在条件边处中断
      - "approve"   → 继续执行 DAG（unattended 模式）
      - "modify"    → 打回 plan_workflow 重新规划
      - "reject"    → 终止流程

本 Node 不做真正的 HTTP 暂停——HTTP 层在 /approve_plan 接口中
注入 human_action 后调用 graph.invoke(resume_state) 恢复执行。

待机：始终写入 pipeline_status = "waiting_approval"（当 action 为空时），
      并返回空 dict 让图在条件边处自然分流。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from application.pipeline.state import PipelineState

logger = logging.getLogger(__name__)


def human_approval_node(state: PipelineState) -> dict[str, Any]:
    """
    LangGraph Node — human_approval

    条件边路由逻辑由 graph.py 中的 should_proceed() 负责；
    本 Node 只负责日志记录和状态持久化。

    当 human_action 为 None 时，图在条件边处分流到 __end__（HTTP 层负责 resume）。
    """
    session_id = state["session_id"]
    action = state.get("human_action")
    plan = state.get("proposed_plan")
    now = _ts()

    if action is None:
        # 首次进入该节点（尚未收到用户响应）
        logger.info(
            "[human_approval] session=%s | awaiting user decision on plan_id=%s",
            session_id,
            plan.plan_id if plan else "N/A",
        )
        return {
            "pipeline_status": "waiting_approval",
            "audit_log": [
                f"[{now}][human_approval] Plan submitted for review: {plan.plan_id if plan else 'N/A'}",
                f"[{now}][human_approval] Waiting for user approval …",
            ],
        }

    # 收到用户响应
    logger.info(
        "[human_approval] session=%s | action='%s'",
        session_id,
        action,
    )

    audit: list[str] = [
        f"[{now}][human_approval] User action received: {action}",
    ]

    if action == "approve":
        audit.append(f"[{now}][human_approval] Plan APPROVED — entering unattended execution")
        status = "approved"
    elif action == "modify":
        audit.append(f"[{now}][human_approval] Plan MODIFY — returning to plan_workflow")
        status = "running"
    else:  # reject
        audit.append(f"[{now}][human_approval] Plan REJECTED — terminating pipeline")
        status = "rejected"

    return {
        "pipeline_status": status,
        "audit_log": audit,
        "updated_at": now,
    }


def _ts() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
