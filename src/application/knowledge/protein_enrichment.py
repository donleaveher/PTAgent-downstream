"""全部已鉴定蛋白的 UniProt 基础注释。"""

from __future__ import annotations

from typing import Any

from pkg.annotation import ProteinAnnotationSource, get_protein_annotation_source
from pkg.experiment import (
    AnnotationTargetType,
    EvidenceLevel,
    ExperimentRepository,
    MetaAnnotation,
    get_experiment_store,
    stable_annotation_id,
)


def enrich_experiment_proteins(
    experiment_id: str,
    *,
    repository: ExperimentRepository | None = None,
    source: ProteinAnnotationSource | None = None,
) -> dict[str, Any]:
    """全量蛋白基础注释先落事实库；图投影由后续 GraphStore 阶段负责。"""

    repo = repository or get_experiment_store()
    context = repo.get_context(experiment_id)
    if context is None:
        raise ValueError(f"unknown experiment_id: {experiment_id}")

    proteins = repo.list_proteins(experiment_id)
    src = source or get_protein_annotation_source()
    accessions = sorted({protein.accession for protein in proteins})
    facts_by_accession = src.fetch(accessions) if accessions else {}

    annotations: dict[str, MetaAnnotation] = {}
    proteins_with_facts = 0
    for protein in proteins:
        facts = facts_by_accession.get(protein.accession, [])
        if facts:
            proteins_with_facts += 1
        for fact in facts:
            provenance = {
                "accession": protein.accession,
                "db_version": src.version,
                **fact.provenance,
            }
            annotation_id = stable_annotation_id(
                experiment_id=experiment_id,
                target_type=AnnotationTargetType.PROTEIN.value,
                target=protein.protein_id,
                attribute=fact.attribute,
                value=fact.value,
                source=src.name,
            )
            annotations[annotation_id] = MetaAnnotation(
                annotation_id=annotation_id,
                experiment_id=experiment_id,
                target=protein.protein_id,
                target_type=AnnotationTargetType.PROTEIN,
                attribute=fact.attribute,
                value=fact.value,
                evidence_level=EvidenceLevel.CONCLUSION,
                source=src.name,
                derivation={"ref": fact.source_ref} if fact.source_ref else {},
                provenance={
                    **provenance,
                    **({"evidence_code": fact.evidence_code} if fact.evidence_code else {}),
                },
            )

    rows = [annotations[key] for key in sorted(annotations)]
    written = repo.add_annotations(rows)
    return {
        "experiment_id": experiment_id,
        "proteins": len(proteins),
        "accessions": len(accessions),
        "proteins_with_facts": proteins_with_facts,
        "missing_accessions": sorted(set(accessions) - set(facts_by_accession)),
        "annotations": len(rows),
        "written": written,
        "source": src.name,
        "source_version": src.version,
    }


__all__ = ["enrich_experiment_proteins"]
