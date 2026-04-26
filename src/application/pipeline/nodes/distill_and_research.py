"""
Node 5: distill_and_research

职责：
  - 对 execute_dag 的结果应用 FilterConfig（前置装填策略）
  - 提炼 KeyFindings（结论摘要）
  - 补充 ResearchEvidence（文献检索）

待机：无人值守，无需人工介入。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from application.pipeline.state import PipelineState

if TYPE_CHECKING:
    from model.http.pipeline import (
        ExecutionResults,
        FilterConfig,
        KeyFinding,
        ResearchEvidence,
    )

logger = logging.getLogger(__name__)


def distill_and_research_node(state: PipelineState) -> dict[str, Any]:
    """
    LangGraph Node — distill_and_research

    工作流程：
      1. 获取 execution_results 和 filter_config_snapshot
      2. 调用 _apply_filter() 对结果做前置过滤
      3. 调用 LLM 生成 KeyFindings（Mock）
      4. 调用 LLM 补充 ResearchEvidence（Mock）
    """
    session_id = state["session_id"]
    results = state.get("execution_results")
    filter_snapshot: dict[str, Any] | None = state.get("filter_config_snapshot")
    now = _ts()

    logger.info("[distill_and_research] session=%s | starting …", session_id)
    audit = [f"[{now}][distill_and_research] Started"]

    if not results:
        logger.warning("[distill_and_research] session=%s | no execution_results", session_id)
        return {
            "pipeline_status": "failed",
            "audit_log": audit + [f"[{_ts()}][distill_and_research] ERROR: no results"],
        }

    # -------------------------------------------------------------------
    # ① 过滤
    # -------------------------------------------------------------------
    fc = _parse_filter_config(filter_snapshot)
    filtered_steps, discarded = _apply_filter(results, fc)
    audit.append(
        f"[{_ts()}][distill_and_research] Filter applied: "
        f"kept={len(filtered_steps)}, discarded={discarded}"
    )
    logger.info(
        "[distill_and_research] session=%s | filter: kept=%d, discarded=%d",
        session_id,
        len(filtered_steps),
        discarded,
    )

    # -------------------------------------------------------------------
    # ② 提炼 KeyFindings（Mock LLM）
    # -------------------------------------------------------------------
    findings = _mock_generate_findings(session_id, filtered_steps)
    audit.append(
        f"[{_ts()}][distill_and_research] KeyFindings generated: {len(findings)}"
    )

    # -------------------------------------------------------------------
    # ③ 补充 ResearchEvidence（Mock LLM）
    # -------------------------------------------------------------------
    evidence = _mock_search_evidence(session_id, findings)
    audit.append(
        f"[{_ts()}][distill_and_research] ResearchEvidence retrieved: {len(evidence)}"
    )

    return {
        "key_findings": findings,
        "research_evidence": evidence,
        "pipeline_status": "running",
        "audit_log": audit,
        "updated_at": _ts(),
    }


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------

def _parse_filter_config(snapshot: dict[str, Any] | None) -> "FilterConfig | None":
    if not snapshot:
        return None
    from model.http.pipeline import FilterConfig
    return FilterConfig.model_validate(snapshot)


def _apply_filter(
    results: "ExecutionResults",
    fc: "FilterConfig | None",
) -> tuple[list[str], int]:
    """
    应用 FilterConfig 到 ExecutionResults。

    返回 (kept_step_ids, discarded_count)
    """
    all_step_ids = list(results.steps.keys())
    if not fc or not fc.enabled:
        return all_step_ids, 0

    kept = all_step_ids  # 简化：Mock 直接全部保留
    # TODO: 后续按 fc.confidence_threshold / top_n / custom_rules 做真实过滤
    return kept, len(all_step_ids) - len(kept)


def _mock_generate_findings(session_id: str, step_ids: list[str]) -> list["KeyFinding"]:
    """【占位】调用 LLM 从执行结果提炼 KeyFindings。"""
    from model.http.pipeline import KeyFinding

    if not step_ids:
        return []

    return [
        KeyFinding(
            finding_id=f"finding_{uuid.uuid4().hex[:6]}",
            topic="蛋白质鉴定结果",
            content=(
                f"基于 {len(step_ids)} 个步骤的执行结果，成功从质谱数据中鉴定了 "
                "一批高置信度肽段，具体结果见附带的 DataObject。"
            ),
            source_steps=step_ids,
            confidence=0.88,
            evidence=["UniProt DB", "DeepXiv literature"],
        ),
        KeyFinding(
            finding_id=f"finding_{uuid.uuid4().hex[:6]}",
            topic="数据质量评估",
            content="肽段覆盖率良好，结果可重复性高，符合后续蛋白组学分析要求。",
            source_steps=step_ids[:1],
            confidence=0.75,
            evidence=["Internal QC metrics"],
        ),
    ]


def _mock_search_evidence(session_id: str, findings: list["KeyFinding"]) -> list["ResearchEvidence"]:
    """【占位】调用 DeepXiv / UniProt 等工具补充文献证据。"""
    from model.http.pipeline import ResearchEvidence

    if not findings:
        return []

    return [
        ResearchEvidence(
            query=findings[0].topic,
            retrieved_chunks=[
                {
                    "title": "Mock Article: Proteomics Methods Review",
                    "chunk": "Recent advances in mass spectrometry have enabled ...",
                    "score": 0.92,
                }
            ],
            citations=["arXiv:mock.2024.001", "PMID:12345678"],
        )
    ]


def _ts() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
