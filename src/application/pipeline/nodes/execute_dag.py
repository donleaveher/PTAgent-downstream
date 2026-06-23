"""
Node 4: execute_dag

职责：
  - 接收 validated WorkflowPlan
  - 调用 DAGCompiler 将 plan 编译为 Run 实例集合
  - 调用 DAGScheduler 按拓扑批次执行（批次内并行，批次间串行）
  - 收集 StepResult，写入 execution_results
  - 全程无人值守（unattended）

调度依赖：
  - application.dag_engine.DAGCompiler
  - application.dag_engine.DAGScheduler
  - pkg.data_plane.store.DataPlaneStore（写入 Run 记录）
  - SSE EventBus（状态推送，见 router/pipeline_router.py）
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from application.pipeline.state import PipelineState

if TYPE_CHECKING:
    from application.dag_engine.compiler import DAGCompiler
    from application.dag_engine.scheduler import DAGScheduler
    from application.dag_engine.models import ExecutionResults
    from model.http.pipeline import StepResult

logger = logging.getLogger(__name__)


def execute_dag_node(state: PipelineState) -> dict[str, Any]:
    """
    LangGraph Node — execute_dag

    工作流程：
      1. 从 proposed_plan 构建 DAGCompiler
      2. 编译得到 step_id → run_id 映射
      3. 启动 DAGScheduler 执行（批次调度）
      4. 收集结果，返回 execution_results

    注意：schedule_fn / compiler_factory 由外部传入（依赖注入），
          避免本模块直接 import 具体实现。
    """
    session_id = state["session_id"]
    plan = state.get("proposed_plan")
    now = _ts()

    if not plan:
        logger.error("[execute_dag] session=%s | proposed_plan is None", session_id)
        return {
            "pipeline_status": "failed",
            "audit_log": [
                f"[{now}][execute_dag] ERROR: no proposed_plan found",
            ],
        }

    plan_id = plan.plan_id or "unknown"
    logger.info(
        "[execute_dag] session=%s | plan_id=%s | steps=%d | starting unattended execution",
        session_id,
        plan_id,
        len(plan.steps),
    )

    audit = [
        f"[{now}][execute_dag] Execution started for plan {plan_id}",
        f"[{now}][execute_dag] Total steps: {len(plan.steps)}",
    ]

    try:
        # -------------------------------------------------------------------
        # ① 编译：WorkflowPlan → step_id → run_id
        # -------------------------------------------------------------------
        compiler = _get_compiler(session_id)
        step_run_ids = compiler.compile(plan)
        audit.append(
            f"[{now}][execute_dag] Compiled {len(step_run_ids)} Run instances"
        )
        logger.info("[execute_dag] session=%s | run_ids=%s", session_id, step_run_ids)

        # -------------------------------------------------------------------
        # ② 调度：拓扑批次执行
        # -------------------------------------------------------------------
        results = _run_scheduler(
            session_id=session_id,
            step_run_ids=step_run_ids,
            plan=plan,
            audit=audit,
        )

        # -------------------------------------------------------------------
        # ③ 汇总结果
        # -------------------------------------------------------------------
        total_duration = sum(
            r.duration_seconds for r in results.steps.values()
        )
        failed_steps = [
            sid for sid, r in results.steps.items() if r.status == "failed"
        ]

        logger.info(
            "[execute_dag] session=%s | completed | total_duration=%.1fs | failed=%s",
            session_id,
            total_duration,
            failed_steps,
        )

        status = "failed" if failed_steps else "running"

        audit.append(
            f"[{_ts()}][execute_dag] Execution finished — "
            f"total_duration={total_duration:.1f}s, failed_steps={failed_steps}"
        )

        return {
            "execution_results": results,
            "pipeline_status": status,
            "audit_log": audit,
            "updated_at": _ts(),
        }

    except Exception as exc:
        logger.exception("[execute_dag] session=%s | unexpected error", session_id)
        return {
            "pipeline_status": "failed",
            "execution_results": None,
            "audit_log": audit + [f"[{_ts()}][execute_dag] ERROR: {exc}"],
            "updated_at": _ts(),
        }


# ---------------------------------------------------------------------------
# 依赖注入桩（后续在 router/pipeline_router.py 中替换为真实实例）
# ---------------------------------------------------------------------------

_compiler_factory: Any = None
_scheduler_factory: Any = None


def register_compiler_factory(factory: Any) -> None:
    """由 application 层在启动时注入真实的 DAGCompiler 工厂。"""
    global _compiler_factory
    _compiler_factory = factory


def register_scheduler_factory(factory: Any) -> None:
    """由 application 层在启动时注入真实的 DAGScheduler 工厂。"""
    global _scheduler_factory
    _scheduler_factory = factory


def _get_compiler(session_id: str) -> Any:
    """【占位】后续替换为: return _compiler_factory(session_id)"""
    from application.dag_engine.compiler import DAGCompiler
    from pkg.data_plane import get_data_plane_store
    store = get_data_plane_store()
    return DAGCompiler(store=store, session_id=session_id)


async def _run_scheduler(
    session_id: str,
    step_run_ids: dict[str, str],
    plan: Any,
    audit: list[str],
) -> Any:
    """
    【占位】运行 DAG Scheduler。

    后续替换为直接调用真实 scheduler：
        scheduler = _scheduler_factory(
            session_id=session_id,
            step_run_ids=step_run_ids,
            plan=plan,
            on_step_update=_publish_step_event,
        )
        return await scheduler.run()

    当前返回 Mock 结果，用于开发期跑通图。
    """
    import asyncio
    from model.http.pipeline import ExecutionResults, StepResult, StepStatus, StepMode

    # 模拟异步执行延迟
    await asyncio.sleep(0.1)

    results: dict[str, StepResult] = {}
    for step in plan.steps:
        results[step.step_id] = StepResult(
            step_id=step.step_id,
            tool_name=step.tool_name,
            status=StepStatus.SUCCESS,
            run_id=step_run_ids.get(step.step_id),
            output_object_ids=[f"dobj_out_{step.step_id}"],
            output_summary=f"Mock output for {step.tool_name}",
            duration_seconds=1.5,
        )
        audit.append(
            f"[{_ts()}][execute_dag] Step {step.step_id} ({step.tool_name}) → SUCCESS"
        )

    return ExecutionResults(steps=results)


def _ts() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
