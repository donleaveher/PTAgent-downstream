"""
Node 6: generate_report

职责：
  - 整合 experiment_context / execution_results / key_findings / research_evidence
  - 生成 FinalReport（Markdown）
  - 写入 COMPLETED 状态，标志科研流完结

待机：无人值守。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from application.pipeline.state import PipelineState

logger = logging.getLogger(__name__)


def generate_report_node(state: PipelineState) -> dict[str, Any]:
    """
    LangGraph Node — generate_report

    工作流程：
      1. 组装报告数据
      2. 调用 LLM 生成 Markdown（Mock）
      3. 持久化 final_report
      4. 写入 COMPLETED 状态
    """
    session_id = state["session_id"]
    ctx = state.get("experiment_context")
    results = state.get("execution_results")
    findings = state.get("key_findings", [])
    evidence = state.get("research_evidence", [])
    now = _ts()

    logger.info("[generate_report] session=%s | starting …", session_id)
    audit = [f"[{now}][generate_report] Started"]

    # -------------------------------------------------------------------
    # ① 生成报告（Mock LLM）
    # -------------------------------------------------------------------
    report = _mock_generate_report(
        session_id=session_id,
        title=ctx.title if ctx else "Untitled Experiment",
        hypothesis=ctx.hypothesis if ctx else "",
        results=results,
        findings=findings,
        evidence=evidence,
    )
    audit.append(f"[{now}][generate_report] Report generated: '{report.title}'")

    # -------------------------------------------------------------------
    # ② 收集附加 DataObject
    # -------------------------------------------------------------------
    attached_dobjs: list[str] = []
    if results:
        for step_result in results.steps.values():
            attached_dobjs.extend(step_result.output_object_ids)
    audit.append(
        f"[{now}][generate_report] Attached DataObjects: {attached_dobjs}"
    )

    logger.info(
        "[generate_report] session=%s | report='%s' | findings=%d | COMPLETED",
        session_id,
        report.title,
        len(findings),
    )

    return {
        "final_report": report,
        "pipeline_status": "completed",
        "audit_log": audit + [f"[{_ts()}][generate_report] Pipeline COMPLETED"],
        "updated_at": _ts(),
    }


# ---------------------------------------------------------------------------
# Mock 报告生成
# ---------------------------------------------------------------------------

def _mock_generate_report(
    session_id: str,
    title: str,
    hypothesis: str,
    results: Any,
    findings: list[Any],
    evidence: list[Any],
) -> Any:
    """【占位】调用 LLM 生成结构化 Markdown 报告。"""
    from model.http.pipeline import FinalReport, ReportSection

    sections = [
        ReportSection(level=1, heading="摘要", content="本研究在假设驱动下完成了蛋白质组学自动化分析流程。"),
        ReportSection(
            level=2,
            heading="研究背景与假设",
            content=hypothesis or "未提供研究假设。",
        ),
        ReportSection(
            level=2,
            heading="方法与工具",
            content=_format_tools_section(results),
        ),
        ReportSection(
            level=2,
            heading="主要结论",
            content="\n\n".join(
                f"**{f.topic}**（置信度: {f.confidence:.0%}）\n{f.content}"
                for f in findings
            ) if findings else "（无有效结论）",
        ),
        ReportSection(
            level=2,
            heading="文献证据",
            content=_format_evidence_section(evidence),
        ),
        ReportSection(
            level=2,
            heading="技术说明",
            content="本报告由 PTAgent 科研流自动化系统生成，所有原始数据均以 DataObject 形式存储于数据平面。",
        ),
    ]

    raw_md = "\n\n".join(
        f"{'#' * s.level} {s.heading}\n\n{s.content}"
        for s in sections
    )

    return FinalReport(
        title=title or "PTAgent 研究报告",
        sections=sections,
        raw_markdown=raw_md,
        attached_data_object_ids=[],
    )


def _format_tools_section(results: Any) -> str:
    if not results or not results.steps:
        return "无工具执行记录。"
    lines = []
    for step_id, res in results.steps.items():
        lines.append(f"- **{step_id}** ({res.tool_name}): {res.output_summary} — {res.status.value}")
    return "\n".join(lines)


def _format_evidence_section(evidence_list: list[Any]) -> str:
    if not evidence_list:
        return "无文献证据。"
    parts = []
    for ev in evidence_list:
        parts.append(f"### 查询: {ev.query}\n")
        for chunk in (ev.retrieved_chunks or []):
            parts.append(f"- *{chunk.get('title', 'Unknown')}* (score={chunk.get('score', 0):.2f})")
        if ev.citations:
            parts.append(f"\n引用: {', '.join(ev.citations)}")
    return "\n".join(parts)


def _ts() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
