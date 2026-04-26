"""
application.dag_engine.scheduler：DAGScheduler

基于 asyncio 的 DAG 执行调度器。

职责：
  - 接收编译后的 step_id → run_id 映射
  - 按拓扑批次调度执行（批次内并行 asyncio.gather，批次间串行）
  - 触发 MCP Client 发起实际计算
  - 监听 Run 状态转移（Pending → Running → Success/Failed）
  - 通过 on_step_update 回调推送 SSE 事件
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Awaitable

from application.dag_engine.models import (
    ExecutionResults,
    StepDependency,
    StepResult,
    StepStatus,
)

if TYPE_CHECKING:
    from model.http.pipeline import WorkflowPlan
    from pkg.data_plane.store import DataPlaneStore

logger = logging.getLogger(__name__)


# 类型别名：每步状态更新回调
StepUpdateCallback = Callable[[StepResult], Awaitable[None]]


class DAGScheduler:
    """
    拓扑批次调度器。

    使用方式：
        scheduler = DAGScheduler(
            store=store,
            session_id=session_id,
            step_run_ids=run_ids,
            plan=plan,
            on_step_update=publish_step_event,
        )
        results = await scheduler.run()
    """

    def __init__(
        self,
        store: "DataPlaneStore",
        session_id: str,
        step_run_ids: dict[str, str],
        plan: "WorkflowPlan",
        on_step_update: StepUpdateCallback | None = None,
    ) -> None:
        self._store = store
        self._session_id = session_id
        self._step_run_ids = step_run_ids
        self._plan = plan
        self._on_update = on_step_update

        self._step_map = {s.step_id: s for s in plan.steps}
        self._results = ExecutionResults()
        self._results.steps = {
            s.step_id: StepResult(step_id=s.step_id, tool_name=s.tool_name)
            for s in plan.steps
        }

        # 拓扑批次
        dep = StepDependency.from_steps([s.model_dump() for s in plan.steps])
        self._batches = dep.batches()

        logger.info(
            "[DAGScheduler] session=%s | batches=%s",
            session_id,
            self._batches,
        )

    # -------------------------------------------------------------------------
    # 公共入口
    # -------------------------------------------------------------------------

    async def run(self) -> ExecutionResults:
        """
        启动调度：按批次执行，返回最终结果。
        """
        logger.info(
            "[DAGScheduler] session=%s | starting | total_batches=%d",
            self._session_id,
            len(self._batches),
        )
        t0 = time.monotonic()

        for batch_idx, batch in enumerate(self._batches):
            logger.info(
                "[DAGScheduler] session=%s | batch %d/%d | steps=%s",
                self._session_id,
                batch_idx + 1,
                len(self._batches),
                batch,
            )
            await self._run_batch(batch)

        elapsed = time.monotonic() - t0
        self._results.total_duration_seconds = elapsed
        logger.info(
            "[DAGScheduler] session=%s | completed | elapsed=%.1fs | success=%d/%d",
            self._session_id,
            elapsed,
            self._results.successful_count(),
            self._results.total_count(),
        )
        return self._results

    # -------------------------------------------------------------------------
    # 批次执行
    # -------------------------------------------------------------------------

    async def _run_batch(self, batch: list[str]) -> None:
        """
        单批次执行：所有步骤并行（asyncio.gather）。

        后续替换 _execute_step 为真实的 MCP Client 调用：
            result = await mcp_client.call_tool(tool_name, resolved_params)
        """
        tasks = [self._execute_step(step_id) for step_id in batch]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _execute_step(self, step_id: str) -> None:
        """
        执行单个步骤。

        步骤：
          1. 更新状态 → RUNNING，触发 callback
          2. 调用 MCP Client（Mock / 真实）
          3. 更新状态 → SUCCESS/FAILED，触发 callback
        """
        run_id = self._step_run_ids.get(step_id)
        step = self._step_map.get(step_id)
        now_iso = _ts()

        result = self._results.steps[step_id]
        result.status = StepStatus.QUEUED
        result.started_at = now_iso
        await self._emit_update(result)

        try:
            # ---- ① 更新 DB 状态 → Pending → Running ----
            self._store.update_run(run_id, status="Running")  # type: ignore[arg-type]

            # ---- ② 执行工具（占位：替换为真实 MCP Client）----
            output = await self._call_mcp_tool(
                tool_name=step.tool_name if step else "",
                run_id=run_id,
            )

            # ---- ③ 成功：更新 DB + 内存状态 ----
            output_dobj_ids = output.get("output_object_ids", [])
            self._store.update_run(
                run_id,                              # type: ignore[arg-type]
                status="Success",
                output_object_ids=output_dobj_ids,
            )

            result.status = StepStatus.SUCCESS
            result.output_object_ids = output_dobj_ids
            result.output_summary = output.get("summary", f"{step.tool_name} completed")
            result.finished_at = _ts()
            result.duration_seconds = _duration(result.started_at, result.finished_at)

            logger.info(
                "[DAGScheduler] session=%s | step=%s | SUCCESS | output=%s",
                self._session_id,
                step_id,
                output_dobj_ids,
            )

        except Exception as exc:
            # ---- ④ 失败：更新 DB + 内存状态 ----
            self._store.update_run(
                run_id,                              # type: ignore[arg-type]
                status="Failed",
                error_log=str(exc),
            )
            result.status = StepStatus.FAILED
            result.error_message = str(exc)
            result.finished_at = _ts()
            result.duration_seconds = _duration(result.started_at, result.finished_at)

            logger.error(
                "[DAGScheduler] session=%s | step=%s | FAILED | %s",
                self._session_id,
                step_id,
                exc,
            )

        await self._emit_update(result)

    # -------------------------------------------------------------------------
    # MCP Client 占位（替换为真实调用）
    # -------------------------------------------------------------------------

    async def _call_mcp_tool(
        self,
        tool_name: str,
        run_id: str | None,
    ) -> dict[str, Any]:
        """
        【占位】调用 MCP Client 执行工具。

        替换方式：
            async with MCPClient(session_id=self._session_id) as client:
                result = await client.call(tool_name, parameters)
                return result

        当前实现：Mock 异步延迟（模拟计算时间）
        """
        # 模拟工具执行耗时（随机 0.5-2s）
        import random
        await asyncio.sleep(random.uniform(0.5, 2.0))

        return {
            "output_object_ids": [f"dobj_out_{run_id}" if run_id else "dobj_out_mock"],
            "summary": f"{tool_name} executed successfully (mock)",
        }

    # -------------------------------------------------------------------------
    # 回调
    # -------------------------------------------------------------------------

    async def _emit_update(self, result: StepResult) -> None:
        """通过回调推送步骤更新（SSE）。"""
        if self._on_update:
            try:
                await self._on_update(result)
            except Exception as exc:
                logger.warning("[DAGScheduler] on_update callback failed: %s", exc)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _duration(start_iso: str, end_iso: str) -> float:
    """计算 ISO 时间字符串之间的秒数差。"""
    try:
        fmt = "%Y-%m-%dT%H:%M:%S.%f%z"
        s = datetime.fromisoformat(start_iso)
        e = datetime.fromisoformat(end_iso)
        return (e - s).total_seconds()
    except Exception:
        return 0.0
