"""
application.dag_engine.compiler：DAGCompiler

将 WorkflowPlan 编译为底层 Run 实例集合。

职责：
  - 解析 WorkflowStep.parameters，将 $ref: 'dobj_xxx' 替换为实际路径
  - 调用 DataPlaneStore.create_run() 创建 Run 记录
  - 返回 step_id → run_id 映射（供 Scheduler 使用）
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from application.dag_engine.models import StepDependency

if TYPE_CHECKING:
    from model.http.pipeline import WorkflowPlan
    from pkg.data_plane.store import DataPlaneStore

logger = logging.getLogger(__name__)

# $ref 引用正则：{ "$ref": "dobj_xxx" }
_REF_PATTERN = re.compile(r'^\$ref:\s*"?([\w\-]+)"?$')


class DAGCompiler:
    """
    WorkflowPlan → Run 实例集合的编译器。

    流程：
      1. 拓扑分析（StepDependency）→ 拓扑批次
      2. 遍历每个 step，将 $ref 参数展开为实际路径
      3. 调用 DataPlaneStore.create_run() 创建 Run
    """

    def __init__(self, store: "DataPlaneStore", session_id: str) -> None:
        self._store = store
        self._session_id = session_id

    def compile(self, plan: "WorkflowPlan") -> dict[str, str]:
        """
        编译 WorkflowPlan，返回 step_id → run_id 映射。

        Raises:
            ValueError: 检测到环（cycle）时抛出
        """
        logger.info(
            "[DAGCompiler] session=%s | plan_id=%s | steps=%d",
            self._session_id,
            plan.plan_id,
            len(plan.steps),
        )

        dep = StepDependency.from_steps([s.model_dump() for s in plan.steps])
        batches = dep.batches()
        step_map = {s.step_id: s for s in plan.steps}

        run_ids: dict[str, str] = {}

        for batch_idx, batch in enumerate(batches):
            logger.info(
                "[DAGCompiler] batch %d/%d | parallel_steps=%s",
                batch_idx + 1,
                len(batches),
                batch,
            )
            for step_id in batch:
                step = step_map[step_id]
                resolved_params = self._resolve_params(step.parameters)
                input_refs = self._extract_refs(step.parameters)

                # 查找实际文件路径（替换 $ref → storage_path）
                input_paths: dict[str, str] = {}
                for ref_id in input_refs:
                    path = self._resolve_ref_to_path(ref_id)
                    if path:
                        input_paths[ref_id] = path

                run_id = self._store.create_run(
                    session_id=self._session_id,
                    tool_name=step.tool_name,
                    run_kind="MCP_IO",       # MCP I/O 类型
                    input_object_ids=list(input_refs),
                    parameters=resolved_params,
                )
                run_ids[step_id] = run_id
                logger.info(
                    "[DAGCompiler] created run | step_id=%s | run_id=%s | tool=%s",
                    step_id,
                    run_id,
                    step.tool_name,
                )

        logger.info(
            "[DAGCompiler] session=%s | compiled %d runs",
            self._session_id,
            len(run_ids),
        )
        return run_ids

    # -------------------------------------------------------------------------
    # 参数展开
    # -------------------------------------------------------------------------

    def _resolve_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        将参数字典中的 $ref 引用替换为实际路径。

        示例：
          输入: {"peptide": {"$ref": "dobj_input_fasta"}, "charge": 2}
          输出: {"peptide": "/data/ptagent/sess_xxx/dobj_input_fasta.fasta", "charge": 2}
        """
        resolved: dict[str, Any] = {}
        for key, value in params.items():
            if isinstance(value, dict) and "$ref" in value:
                ref_id = value["$ref"]
                path = self._resolve_ref_to_path(ref_id)
                resolved[key] = path if path else value
            else:
                resolved[key] = value
        return resolved

    def _extract_refs(self, params: dict[str, Any]) -> set[str]:
        """从参数字典中提取所有 $ref 引用的 ID。"""
        refs: set[str] = set()

        def _walk(v: Any) -> None:
            if isinstance(v, dict):
                if "$ref" in v:
                    ref_raw = str(v["$ref"])
                    m = _REF_PATTERN.match(ref_raw)
                    if m:
                        refs.add(m.group(1))
                    else:
                        refs.add(ref_raw)
                for child in v.values():
                    _walk(child)
            elif isinstance(v, list):
                for item in v:
                    _walk(item)

        _walk(params)
        return refs

    def _resolve_ref_to_path(self, ref_id: str) -> str | None:
        """
        将 DataObject ID / data_ref 键名解析为实际存储路径。

        优先级：
          1. data_refs 局部引用（Node 间传递的命名引用）
          2. DataPlaneStore.get_data_object() — 全局 DataObject
          3. 直接返回 ref_id（兜底：认为是字符串路径）
        """
        try:
            obj = self._store.get_data_object(ref_id)
            if obj:
                return obj.get("storage_path", ref_id)
        except Exception:
            pass
        # 兜底：直接返回原值
        return ref_id
