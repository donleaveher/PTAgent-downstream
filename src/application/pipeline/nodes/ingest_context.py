"""
Node 1: ingest_context

职责：
  - 接收并验证 experiment_context（已在 HTTP 层做 Pydantic 校验）
  - 将 DataObject ID 列表注册到 data_refs
  - 持久化 initial state 到 SQLite
  - 记录审计日志

待机：返回 update dict，由 graph.compile() 合并进状态。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from application.pipeline.state import PipelineState

logger = logging.getLogger(__name__)


def ingest_context_node(state: PipelineState) -> dict[str, Any]:
    """
    LangGraph Node — ingest_context

    输入 state 必须包含 experiment_context。
    输出增量 update dict。
    """
    session_id = state["session_id"]
    ctx = state.get("experiment_context")

    if ctx is None:
        logger.error("[ingest_context] experiment_context is None, session=%s", session_id)
        return {
            "pipeline_status": "failed",
            "audit_log": [f"[{_ts()}][ingest_context] ERROR: experiment_context missing"],
        }

    logger.info(
        "[ingest_context] session=%s | title='%s' | data_objects=%s",
        session_id,
        ctx.title,
        ctx.data_object_ids,
    )

    # 将 data_object_ids 注册到 data_refs（命名引用后续由 plan_workflow 填充）
    data_refs: dict[str, str] = {}
    for i, dobj_id in enumerate(ctx.data_object_ids):
        data_refs[f"input_{i}"] = dobj_id

    now = _ts()
    audit_entries = [
        f"[{now}][ingest_context] Context received: title='{ctx.title}'",
        f"[{now}][ingest_context] DataObject IDs registered: {list(data_refs.values())}",
    ]
    if ctx.filter_config.enabled:
        audit_entries.append(
            f"[{now}][ingest_context] FilterConfig active: "
            f"confidence={ctx.filter_config.confidence_threshold}, "
            f"top_n={ctx.filter_config.top_n}, "
            f"custom_rules={len(ctx.filter_config.custom_rules)}"
        )
    else:
        audit_entries.append(f"[{now}][ingest_context] FilterConfig disabled")

    # 快照 filter_config（确保 approve 后不再被用户修改）
    filter_config_snapshot = (
        ctx.filter_config.model_dump() if ctx.filter_config else None
    )

    return {
        "data_refs": data_refs,
        "pipeline_status": "running",
        "audit_log": audit_entries,
        "filter_config_snapshot": filter_config_snapshot,
        "updated_at": now,
    }


def _ts() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
