"""疾病过表达富集应用服务：差异蛋白 vs 背景(全部鉴定蛋白)，基因集取自 CTD 结论。

结果作为**集合层统计结论**持久化到 `enrichment_result`（独立于单实体 MetaAnnotation），
并随结果记录 study/background 集合 checksum 与基因集来源版本，使富集可复现、可审计。
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any

from pkg.analysis import over_representation
from pkg.experiment import (
    AnnotationTargetType,
    EnrichmentRecord,
    EvidenceLevel,
    ExperimentRepository,
    get_experiment_store,
)

_GENE_SET_SOURCE = "CTD"


def _gene_set_checksum(genes: set[str]) -> str:
    """对基因集合算稳定 SHA-256（排序后规范化），用于复现/审计。"""

    canonical = json.dumps(sorted(genes), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run_disease_enrichment(
    experiment_id: str,
    *,
    repository: ExperimentRepository | None = None,
    q_threshold: float = 0.05,
    min_overlap: int = 2,
    persist: bool = True,
) -> dict[str, Any]:
    """对差异蛋白基因做 CTD 疾病过表达；背景 = 本次全部鉴定蛋白基因（Q1）。

    基因集来自仓库里已有的 CTD 直接结论（需先跑 M1 disease_annotation）。
    `persist=True` 时把全量结果（非仅显著项）幂等写入 `enrichment_result`。
    """

    repo = repository or get_experiment_store()
    context = repo.get_context(experiment_id)
    if context is None:
        raise ValueError(f"unknown experiment_id: {experiment_id}")

    proteins = repo.list_proteins(experiment_id)
    gene_by_protein = {p.protein_id: p.gene for p in proteins}
    background = {p.gene for p in proteins if p.gene}

    study = {
        gene_by_protein[d.protein_id]
        for d in repo.list_differentials(experiment_id)
        if d.is_differential and gene_by_protein.get(d.protein_id)
    }

    gene_sets: dict[str, set[str]] = defaultdict(set)
    term_names: dict[str, str] = {}
    gene_set_version = ""
    for ann in repo.list_annotations(experiment_id):
        if (
            ann.evidence_level is EvidenceLevel.CONCLUSION
            and ann.target_type is AnnotationTargetType.GENE
            and ann.source == _GENE_SET_SOURCE
            and isinstance(ann.value, dict)
        ):
            disease_id = ann.value.get("disease_id")
            if disease_id:
                gene_sets[disease_id].add(ann.target)
                term_names[disease_id] = ann.value.get("disease_name") or disease_id
                if not gene_set_version:
                    gene_set_version = str(ann.provenance.get("db_version", ""))

    results = over_representation(
        study,
        background,
        dict(gene_sets),
        term_names=term_names,
        min_overlap=min_overlap,
    )
    enriched = [e for e in results if e.q_value <= q_threshold]

    study_checksum = _gene_set_checksum(study)
    background_checksum = _gene_set_checksum(background)
    records = [
        EnrichmentRecord(
            experiment_id=experiment_id,
            term=e.term,
            term_name=e.term_name,
            term_type="disease",
            overlap=e.overlap,
            study_size=e.study_size,
            background_size=e.background_size,
            term_size=e.term_size,
            p_value=e.p_value,
            q_value=e.q_value,
            fold_enrichment=e.fold_enrichment,
            is_significant=e.q_value <= q_threshold,
            gene_set_source=_GENE_SET_SOURCE,
            gene_set_version=gene_set_version,
            study_checksum=study_checksum,
            background_checksum=background_checksum,
            meta={"overlap_genes": list(e.overlap_genes)},
        )
        for e in results
    ]
    written = repo.add_enrichments(records) if persist else 0

    return {
        "experiment_id": experiment_id,
        "background_size": len(background),
        "study_size": len(study),
        "terms_tested": len(results),
        "enriched": len(enriched),
        "written": written,
        "study_checksum": study_checksum,
        "background_checksum": background_checksum,
        "gene_set_source": _GENE_SET_SOURCE,
        "gene_set_version": gene_set_version,
        "results": [
            {
                "term": e.term,
                "term_name": e.term_name,
                "overlap": e.overlap,
                "term_size": e.term_size,
                "p_value": e.p_value,
                "q_value": e.q_value,
                "fold_enrichment": e.fold_enrichment,
            }
            for e in results
        ],
    }


__all__ = ["run_disease_enrichment"]
