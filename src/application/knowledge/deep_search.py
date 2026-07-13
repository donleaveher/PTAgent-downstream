"""Deep-search 证据验证：推动蛋白级疾病假说的认知态跃迁（L4 §8）。

对每条 `MetaAnnotation(HYPOTHESIS)`（M3 结构类比产物）发起在线检索，按证据立场裁决：
支持→`CONCLUSION`、反证→`REFUTED`、冲突/无证据→保持 `HYPOTHESIS`（显式记录未决）。
每次裁决追加 `AnnotationHistory`（保留来源/查询/版本，可完整回放），跃迁时回写
`evidence_level` 并把 deep-search 依据写入 `derivation`。

幂等：已跃迁出 `HYPOTHESIS` 的注释不再处理；`AnnotationHistory` 用确定性 `history_id`
去重——同一证据重复处理不产生重复历史。deep-search 只更新实验工作区的 Annotation/历史，
不触碰通用 KG（§7.3 / §8.2）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from pkg.deep_search import (
    DeepSearchTask,
    EvidenceRecord,
    LiteratureSearchSource,
    VerdictOutcome,
    decide_verdict,
    get_literature_search_source,
)
from pkg.experiment import (
    AnnotationHistory,
    AnnotationTargetType,
    DeepSearchEvidence,
    EvidenceLevel,
    ExperimentRepository,
    MetaAnnotation,
    get_experiment_store,
)

_SOURCE = "deep-search"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _build_query(task_fields: dict[str, Any]) -> str:
    """确定性查询串（便于溯源/复跑）。"""

    parts = [
        task_fields.get("gene") or task_fields.get("protein_id", ""),
        task_fields.get("disease_name") or task_fields.get("disease_id", ""),
        task_fields.get("organism", ""),
        task_fields.get("tissue", ""),
    ]
    return " | ".join(p for p in parts if p)


def _candidate_genes(annotation: MetaAnnotation, *, primary_gene: str) -> tuple[str, ...]:
    """按候选融合排名提取近邻基因，供原始基因零命中的补充检索。"""

    derivation = annotation.derivation if isinstance(annotation.derivation, dict) else {}
    neighbors = derivation.get("neighbors")
    ordered_neighbors = neighbors if isinstance(neighbors, list) else []
    ordered_neighbors = sorted(
        (row for row in ordered_neighbors if isinstance(row, dict)),
        key=lambda row: (
            int(row.get("fusion_rank") or 10**9),
            -float(row.get("fused_score") or 0.0),
            str(row.get("accession") or ""),
        ),
    )
    raw_genes = [row.get("gene") for row in ordered_neighbors]
    via_genes = derivation.get("via_genes")
    if isinstance(via_genes, list):
        raw_genes.extend(via_genes)

    primary = primary_gene.strip().casefold()
    seen: set[str] = set()
    out: list[str] = []
    for raw_gene in raw_genes:
        gene = str(raw_gene or "").strip()
        key = gene.casefold()
        if not gene or key == primary or key in seen:
            continue
        seen.add(key)
        out.append(gene)
    return tuple(out)


def _stable_evidence_id(
    *,
    experiment_id: str,
    annotation_id: str,
    evidence: EvidenceRecord,
    source_version: str,
    query: str,
) -> str:
    """同一检索任务返回的同一证据映射到同一不可变证据行。"""

    canonical = json.dumps(
        {
            "experiment_id": experiment_id,
            "annotation_id": annotation_id,
            "stance": evidence.stance.value,
            "title": evidence.title,
            "reference": evidence.reference,
            "source": evidence.source,
            "source_version": source_version,
            "snippet": evidence.snippet,
            "query": query,
            "provenance": evidence.provenance,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"dse_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:32]}"


def _materialize_evidence(
    *,
    experiment_id: str,
    annotation_id: str,
    query: str,
    source_name: str,
    source_version: str,
    evidence: Sequence[EvidenceRecord],
) -> list[DeepSearchEvidence]:
    """把外部检索记录校验并转为可持久化、稳定标识的证据行。"""

    rows: dict[str, DeepSearchEvidence] = {}
    for record in evidence:
        if not record.title or not record.reference or not record.source:
            raise ValueError(
                "deep-search evidence requires non-empty title, reference, and source"
            )
        evidence_id = _stable_evidence_id(
            experiment_id=experiment_id,
            annotation_id=annotation_id,
            evidence=record,
            source_version=source_version,
            query=query,
        )
        rows[evidence_id] = DeepSearchEvidence(
            evidence_id=evidence_id,
            experiment_id=experiment_id,
            annotation_id=annotation_id,
            stance=record.stance.value,
            title=record.title,
            reference=record.reference,
            source=record.source,
            source_version=source_version,
            snippet=record.snippet,
            query=query,
            provenance={
                "search_source": source_name,
                "search_source_version": source_version,
                **record.provenance,
            },
        )
    return [rows[evidence_id] for evidence_id in sorted(rows)]


def _stable_history_id(
    annotation_id: str,
    outcome: VerdictOutcome,
    source_version: str,
    evidence_ids: Sequence[str],
) -> str:
    """同一注释 + 裁决 + 证据集 + 源版本 → 同一 history_id，使历史追加幂等。"""

    canonical = json.dumps(
        {
            "annotation_id": annotation_id,
            "verdict": outcome.verdict.value,
            "support_refs": list(outcome.support_refs),
            "refute_refs": list(outcome.refute_refs),
            "source_version": source_version,
            "evidence_ids": sorted(evidence_ids),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"ah_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:32]}"


def verify_experiment_hypotheses(
    experiment_id: str,
    *,
    repository: ExperimentRepository | None = None,
    source: LiteratureSearchSource | None = None,
    annotation_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """对实验内全部（或指定）蛋白级疾病假说跑 deep-search 裁决，幂等落库。

    `annotation_ids` 限定处理范围（默认全部 HYPOTHESIS 注释）。
    """

    repo = repository or get_experiment_store()
    context = repo.get_context(experiment_id)
    if context is None:
        raise ValueError(f"unknown experiment_id: {experiment_id}")

    src = source or get_literature_search_source()
    proteins = {p.protein_id: p for p in repo.list_proteins(experiment_id)}
    existing_history_ids = {
        h.history_id for h in repo.list_annotation_history(experiment_id)
    }
    existing_evidence_ids = {
        row.evidence_id for row in repo.list_deep_search_evidence(experiment_id)
    }

    wanted = set(annotation_ids) if annotation_ids is not None else None
    targets = [
        ann
        for ann in repo.list_annotations(experiment_id)
        if ann.evidence_level is EvidenceLevel.HYPOTHESIS
        and ann.target_type is AnnotationTargetType.PROTEIN
        and isinstance(ann.value, dict)
        and ann.value.get("disease_id")
        and (wanted is None or ann.annotation_id in wanted)
    ]

    updated: dict[str, MetaAnnotation] = {}
    new_history: list[AnnotationHistory] = []
    new_evidence: dict[str, DeepSearchEvidence] = {}
    counts = {"supported": 0, "refuted": 0, "conflicting": 0, "insufficient": 0}
    evidence_records = 0

    for ann in targets:
        protein = proteins.get(ann.target)
        gene = protein.gene if protein else ""
        organism = protein.organism if protein else context.organism
        taxon_id = protein.taxon_id if protein else context.taxon_id
        disease_id = ann.value["disease_id"]
        disease_name = ann.value.get("disease_name", "")
        query = _build_query(
            {
                "gene": gene,
                "protein_id": ann.target,
                "disease_id": disease_id,
                "disease_name": disease_name,
                "organism": organism,
            }
        )
        task = DeepSearchTask(
            annotation_id=ann.annotation_id,
            experiment_id=experiment_id,
            protein_id=ann.target,
            gene=gene,
            disease_id=disease_id,
            disease_name=disease_name,
            organism=organism,
            taxon_id=taxon_id,
            background=context.raw_text,
            query=query,
            candidate_genes=_candidate_genes(ann, primary_gene=gene),
        )
        evidence: list[EvidenceRecord] = list(src.search(task))
        evidence_rows = _materialize_evidence(
            experiment_id=experiment_id,
            annotation_id=ann.annotation_id,
            query=query,
            source_name=src.name,
            source_version=src.version,
            evidence=evidence,
        )
        evidence_records += len(evidence_rows)
        for row in evidence_rows:
            if row.evidence_id not in existing_evidence_ids:
                new_evidence[row.evidence_id] = row
                existing_evidence_ids.add(row.evidence_id)
        outcome = decide_verdict(ann.evidence_level, evidence)
        counts[outcome.verdict.value] += 1

        evidence_ref = {
            "verdict": outcome.verdict.value,
            "support_refs": list(outcome.support_refs),
            "refute_refs": list(outcome.refute_refs),
            "source": src.name,
            "source_version": src.version,
            "query": query,
            "evidence_ids": [row.evidence_id for row in evidence_rows],
        }
        history_id = _stable_history_id(
            ann.annotation_id,
            outcome,
            src.version,
            evidence_ref["evidence_ids"],
        )
        if history_id not in existing_history_ids:
            new_history.append(
                AnnotationHistory(
                    history_id=history_id,
                    annotation_id=ann.annotation_id,
                    experiment_id=experiment_id,
                    from_level=ann.evidence_level,
                    to_level=outcome.to_level,
                    verdict=outcome.verdict.value,
                    evidence_ref=evidence_ref,
                )
            )
            existing_history_ids.add(history_id)

        if outcome.changed:
            updated[ann.annotation_id] = ann.model_copy(
                update={
                    "evidence_level": outcome.to_level,
                    "updated_at": _utcnow(),
                    "derivation": {**ann.derivation, "deep_search": evidence_ref},
                }
            )

    evidence_written = repo.add_deep_search_evidence(
        [new_evidence[evidence_id] for evidence_id in sorted(new_evidence)]
    )
    written = repo.add_annotations([updated[k] for k in sorted(updated)])
    for history in new_history:
        repo.append_annotation_history(history)

    return {
        "experiment_id": experiment_id,
        "hypotheses": len(targets),
        "verdicts": counts,
        "promoted_to_conclusion": counts["supported"],
        "refuted": counts["refuted"],
        "still_hypothesis": counts["conflicting"] + counts["insufficient"],
        "annotations_updated": written,
        "history_appended": len(new_history),
        "evidence_records": evidence_records,
        "evidence_written": evidence_written,
        "source": src.name,
        "source_version": src.version,
    }


def override_hypothesis_verdict(
    experiment_id: str,
    annotation_id: str,
    *,
    to_level: EvidenceLevel,
    operator: str,
    reason: str,
    repository: ExperimentRepository | None = None,
) -> MetaAnnotation:
    """人工复核/覆盖某条注释的证据等级，保留操作者与理由（§8.2）。"""

    if not operator or not reason:
        raise ValueError("manual override requires operator and reason")

    repo = repository or get_experiment_store()
    annotations = {a.annotation_id: a for a in repo.list_annotations(experiment_id)}
    ann = annotations.get(annotation_id)
    if ann is None:
        raise ValueError(f"unknown annotation_id: {annotation_id}")

    evidence_ref = {"operator": operator, "reason": reason, "source": _SOURCE}
    updated = ann.model_copy(
        update={
            "evidence_level": to_level,
            "updated_at": _utcnow(),
            "derivation": {**ann.derivation, "manual_override": evidence_ref},
        }
    )
    repo.add_annotations([updated])
    repo.append_annotation_history(
        AnnotationHistory(
            annotation_id=annotation_id,
            experiment_id=experiment_id,
            from_level=ann.evidence_level,
            to_level=to_level,
            verdict=f"manual_override:{operator}",
            evidence_ref=evidence_ref,
        )
    )
    return updated


__all__ = ["override_hypothesis_verdict", "verify_experiment_hypotheses"]
