"""全部已鉴定蛋白对应基因的 CTD 直接疾病结论。

与 `protein_enrichment` 对称：那边是蛋白属性（target=protein），这边是疾病关联
（target=gene，Q3 双节点）。直接命中（curated/marker/therapeutic）= 结论级。
"""

from __future__ import annotations

from typing import Any

from pkg.disease import GeneDiseaseSource, get_disease_source
from pkg.experiment import (
    AnnotationTargetType,
    EvidenceLevel,
    ExperimentRepository,
    MetaAnnotation,
    get_experiment_store,
    stable_annotation_id,
)


def annotate_experiment_diseases(
    experiment_id: str,
    *,
    repository: ExperimentRepository | None = None,
    source: GeneDiseaseSource | None = None,
) -> dict[str, Any]:
    """全部蛋白对应基因的 CTD 直接命中 → 基因级 MetaAnnotation(CONCLUSION)，幂等落库。

    跨物种借用是 M2/M3 的假说路径，不在此直接证据链中混入。
    """

    repo = repository or get_experiment_store()
    context = repo.get_context(experiment_id)
    if context is None:
        raise ValueError(f"unknown experiment_id: {experiment_id}")

    proteins = repo.list_proteins(experiment_id)
    src = source or get_disease_source()
    genes = sorted({protein.gene for protein in proteins})
    facts_by_gene = src.fetch(genes) if genes else {}

    annotations: dict[str, MetaAnnotation] = {}
    for protein in proteins:
        for fact in facts_by_gene.get(protein.gene, []):
            attribute = f"disease:{fact.disease_id}"
            value = {"disease_id": fact.disease_id, "disease_name": fact.disease_name}
            annotation_id = stable_annotation_id(
                experiment_id=experiment_id,
                target_type=AnnotationTargetType.GENE.value,
                target=protein.gene,
                attribute=attribute,
                value=value,
                source=src.name,
            )
            annotations[annotation_id] = MetaAnnotation(
                annotation_id=annotation_id,
                experiment_id=experiment_id,
                target=protein.gene,
                target_type=AnnotationTargetType.GENE,
                attribute=attribute,
                value=value,
                evidence_level=EvidenceLevel.CONCLUSION,
                source=src.name,
                derivation={
                    "evidence_type": fact.evidence_type,
                    "relation_id": fact.relation_id,
                    "pubmed_ids": list(fact.pubmed_ids),
                },
                provenance={"gene": protein.gene, "db_version": src.version, **fact.provenance},
            )

    rows = [annotations[key] for key in sorted(annotations)]
    written = repo.add_annotations(rows)
    return {
        "experiment_id": experiment_id,
        "proteins": len(proteins),
        "genes": len(genes),
        "genes_with_disease": len(set(facts_by_gene)),
        "genes_without_disease": sorted(set(genes) - set(facts_by_gene)),
        "annotations": len(rows),
        "written": written,
        "source": src.name,
        "source_version": src.version,
    }


__all__ = ["annotate_experiment_diseases"]
