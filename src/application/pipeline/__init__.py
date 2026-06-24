"""application.pipeline：旧版科研流 LangGraph 主图包（**已弃用 / DEPRECATED**）。

.. deprecated::
   旧上游 / Mock 主线（``plan_workflow`` / ``execute_dag`` / ``distill_and_research`` /
   ``generate_report`` 等节点为 Mock）。已被新版下游编排
   :mod:`application.orchestration`（``run_downstream_pipeline``，§11.2）整体替代。
   当前 src 与 tests 已确认无引用；本包仅作历史保留，**新代码请勿引用**，
   待确认确无外部依赖后整体移除（§13）。
"""

from __future__ import annotations

import warnings

from application.pipeline.graph import build_pipeline_graph
from application.pipeline.state import PipelineState

warnings.warn(
    "application.pipeline 是旧版 Mock LangGraph 主线，已弃用；"
    "请改用 application.orchestration.run_downstream_pipeline（§11.2 / §13）。",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["build_pipeline_graph", "PipelineState"]
