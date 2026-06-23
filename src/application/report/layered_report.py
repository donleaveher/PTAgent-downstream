"""分层报告：从冻结快照生成可审计 Markdown 报告（§10 / L6）。

报告**只从指定冻结快照的 manifest 读取**（不碰活库），先校验快照完整性（防篡改），
再按 结论/假说/伪理/未决 分层呈现，每条重要陈述带 annotation_id + 来源 + 版本/引用。
区分公共事实（CTD 基因结论、UniProt 蛋白基础注释）、实验观察（差异/富集）与推导假说。
正文以差异蛋白与证据分级为重点，附录保留全部蛋白基础注释。

因只读冻结内容，**同一快照重复生成结果稳定**（report checksum 不变）。报告 artifact
落库（独立报告表）暂留后续。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from application.experiment.freeze import verify_snapshot_integrity
from pkg.experiment import ExperimentRepository, ExperimentSnapshot, get_experiment_store


@dataclass(frozen=True)
class ExperimentReport:
    experiment_id: str
    snapshot_id: str
    snapshot_version: str
    markdown: str
    checksum: str               # markdown 的 SHA-256
    sections: tuple[str, ...]   # 章节标题（便于断言/导航）


def _source_label(ann: dict[str, Any]) -> str:
    prov = ann.get("provenance") or {}
    version = (
        prov.get("db_version")
        or prov.get("ctd_version")
        or prov.get("structure_version")
        or prov.get("source_version")
        or ""
    )
    return f"{ann.get('source', '')}" + (f" (v{version})" if version else "")


def _is_disease(ann: dict[str, Any]) -> bool:
    return str(ann.get("attribute", "")).startswith("disease:")


def _fmt_num(value: Any) -> str:
    return f"{value:.3g}" if isinstance(value, (int, float)) else "—"


def _render_markdown(snapshot: ExperimentSnapshot) -> tuple[str, tuple[str, ...]]:
    m = snapshot.manifest
    ctx = m.get("context", {})
    ev = m.get("evidence_levels", {})
    versions = m.get("versions", {})
    annotations = m.get("annotations", [])
    history = m.get("annotation_history", [])

    latest_verdict: dict[str, dict[str, Any]] = {}
    for entry in history:  # manifest 中历史已按 changed_at 排序
        latest_verdict[entry["annotation_id"]] = entry

    disease_conclusions = [a for a in annotations if _is_disease(a) and a["evidence_level"] == "CONCLUSION"]
    disease_hypotheses = [a for a in annotations if _is_disease(a) and a["evidence_level"] == "HYPOTHESIS"]
    disease_refuted = [a for a in annotations if _is_disease(a) and a["evidence_level"] == "REFUTED"]
    base_annotations = [a for a in annotations if not _is_disease(a)]

    lines: list[str] = []
    sections: list[str] = []

    def section(title: str) -> None:
        sections.append(title)
        lines.append(f"## {title}")

    lines.append(f"# 实验报告 — {snapshot.experiment_id}")
    lines.append("")
    lines.append(
        f"> 快照 `{snapshot.snapshot_version}` · 冻结于 {snapshot.frozen_at.isoformat()} "
        f"· 校验值 `{snapshot.checksum[:12]}…`  "
    )
    lines.append(
        f"> pipeline `{versions.get('pipeline_version', '')}` · "
        f"model `{versions.get('model_version') or '—'}`  "
    )
    lines.append(
        f"> 证据分布:结论 {ev.get('CONCLUSION', 0)} · 假说 {ev.get('HYPOTHESIS', 0)} "
        f"· 伪理 {ev.get('REFUTED', 0)}"
    )
    lines.append("")

    section("1. 实验设计")
    lines.append(f"- 标题:{ctx.get('title') or '—'}")
    lines.append(f"- 疾病:{', '.join(ctx.get('disease') or []) or '—'}")
    lines.append(f"- 通路:{', '.join(ctx.get('pathway') or []) or '—'}")
    lines.append(f"- 物种:{ctx.get('organism') or '—'}")
    lines.append(f"- 实验类型:{ctx.get('assay') or '—'}")
    lines.append("")

    section("2. 差异结果（实验观察）")
    diffs = [d for d in m.get("differentials", []) if d.get("is_differential")]
    if diffs:
        lines.append("| 蛋白 | log2FC | 方向 | q 值 |")
        lines.append("|---|---|---|---|")
        for d in diffs:
            lines.append(
                f"| {d['protein_id']} | {_fmt_num(d.get('log2fc'))} | "
                f"{d.get('direction', '')} | {_fmt_num(d.get('q_value'))} |"
            )
    else:
        lines.append("_无显著差异蛋白。_")
    lines.append("")

    section("3. 富集结果（实验观察）")
    enriched = [e for e in m.get("enrichments", []) if e.get("is_significant")]
    if enriched:
        lines.append("| 疾病/通路 | 命中 | 集合 | 富集倍数 | q 值 |")
        lines.append("|---|---|---|---|---|")
        for e in enriched:
            lines.append(
                f"| {e.get('term_name', '')} (`{e['term']}`) | {e.get('overlap')} "
                f"| {e.get('term_size')} | {_fmt_num(e.get('fold_enrichment'))} "
                f"| {_fmt_num(e.get('q_value'))} |"
            )
        first = enriched[0]
        lines.append("")
        lines.append(
            f"> 基因集来源 {first.get('gene_set_source', '')} · "
            f"study/背景 checksum `{(first.get('study_checksum') or '')[:8]}…`/"
            f"`{(first.get('background_checksum') or '')[:8]}…`"
        )
    else:
        lines.append("_无显著富集项。_")
    lines.append("")

    section("4. 结论（公共事实）")
    if disease_conclusions:
        for a in disease_conclusions:
            v = a.get("value") or {}
            lines.append(
                f"- 基因 **{a['target']}** → {v.get('disease_name', '')} "
                f"(`{v.get('disease_id', '')}`) — {_source_label(a)} · `{a['annotation_id']}`"
            )
    else:
        lines.append("_无。_")
    lines.append("")

    section("5. 假说（结构类比推导）")
    if disease_hypotheses:
        for a in disease_hypotheses:
            v = a.get("value") or {}
            der = a.get("derivation") or {}
            via = ", ".join(der.get("via_genes") or [])
            conf = der.get("confidence")
            conf_text = f" · 置信 {conf:.3g}" if isinstance(conf, (int, float)) else ""
            lines.append(
                f"- 蛋白 **{a['target']}** → {v.get('disease_name', '')} "
                f"(`{v.get('disease_id', '')}`) — 经由近邻基因 {via or '—'}{conf_text} "
                f"· {_source_label(a)} · `{a['annotation_id']}`"
            )
    else:
        lines.append("_无。_")
    lines.append("")

    section("6. 伪理（已反驳）")
    if disease_refuted:
        for a in disease_refuted:
            v = a.get("value") or {}
            verdict = latest_verdict.get(a["annotation_id"], {})
            refs = ", ".join((verdict.get("evidence_ref") or {}).get("refute_refs") or [])
            lines.append(
                f"- 蛋白 **{a['target']}** → {v.get('disease_name', '')} "
                f"(`{v.get('disease_id', '')}`) — 反证 {refs or '—'} · `{a['annotation_id']}`"
            )
    else:
        lines.append("_无。_")
    lines.append("")

    section("7. 未决项")
    undetermined = [
        a
        for a in disease_hypotheses
        if latest_verdict.get(a["annotation_id"], {}).get("verdict")
        in ("insufficient", "conflicting")
    ]
    if undetermined:
        for a in undetermined:
            v = a.get("value") or {}
            verdict = latest_verdict.get(a["annotation_id"], {}).get("verdict", "")
            lines.append(
                f"- 蛋白 **{a['target']}** → {v.get('disease_name', '')} "
                f"(`{v.get('disease_id', '')}`) — deep-search 裁决:{verdict} · `{a['annotation_id']}`"
            )
    else:
        lines.append("_无。_")
    lines.append("")

    section("附录 A. 全部蛋白基础注释")
    if base_annotations:
        for a in base_annotations:
            lines.append(
                f"- {a['target']} · {a['attribute']} = {str(a.get('value'))[:80]} "
                f"— {_source_label(a)} · `{a['annotation_id']}`"
            )
    else:
        lines.append("_无。_")
    lines.append("")

    return "\n".join(lines), tuple(sections)


def generate_experiment_report(
    experiment_id: str,
    snapshot_version: str,
    *,
    repository: ExperimentRepository | None = None,
) -> ExperimentReport:
    """从指定冻结快照生成分层 Markdown 报告；快照完整性校验失败则拒绝出报告。"""

    repo = repository or get_experiment_store()
    snapshot = next(
        (
            s
            for s in repo.list_snapshots(experiment_id)
            if s.snapshot_version == snapshot_version
        ),
        None,
    )
    if snapshot is None:
        raise ValueError(
            f"unknown snapshot version {snapshot_version!r} for experiment {experiment_id}"
        )
    if not verify_snapshot_integrity(snapshot):
        raise ValueError(
            f"snapshot {snapshot_version} failed integrity check; refusing to report"
        )

    markdown, sections = _render_markdown(snapshot)
    checksum = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    return ExperimentReport(
        experiment_id=experiment_id,
        snapshot_id=snapshot.snapshot_id,
        snapshot_version=snapshot_version,
        markdown=markdown,
        checksum=checksum,
        sections=sections,
    )


__all__ = ["ExperimentReport", "generate_experiment_report"]
