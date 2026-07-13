"""Generate protein-level hypotheses from persisted fused neighbor candidates."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pkg.disease import GeneDiseaseSource, GeneResolver, get_disease_source, get_gene_resolver
from pkg.experiment import (
    AnnotationTargetType,
    EvidenceLevel,
    ExperimentRepository,
    FusedCandidate,
    MetaAnnotation,
    get_experiment_store,
    stable_annotation_id,
)

_SOURCE = "NeighborFusion"


def generate_experiment_hypotheses(
    experiment_id: str,
    *,
    repository: ExperimentRepository | None = None,
    gene_resolver: GeneResolver | None = None,
    disease_source: GeneDiseaseSource | None = None,
    protein_ids: Iterable[str] | None = None,
    top_k: int | None = None,
) -> dict[str, Any]:
    """Generate protein-level hypotheses from persisted `FusedCandidate` rows.

    Neighbor retrieval and fusion must already have been run by the neighbor
    search layer. This function only performs evidence transfer:

    fused target accession -> gene resolver -> CTD disease -> HYPOTHESIS.
    """

    if top_k is not None and top_k < 1:
        raise ValueError("top_k must be positive")

    repo = repository or get_experiment_store()
    context = repo.get_context(experiment_id)
    if context is None:
        raise ValueError(f"unknown experiment_id: {experiment_id}")

    proteins = repo.list_proteins(experiment_id)
    if protein_ids is not None:
        wanted = set(protein_ids)
        proteins = [protein for protein in proteins if protein.protein_id in wanted]
    if not proteins:
        return _empty_summary(experiment_id, proteins=0)

    resolver = gene_resolver or get_gene_resolver()
    diseases = disease_source or get_disease_source()

    concluded = {
        (ann.target, ann.value.get("disease_id"))
        for ann in repo.list_annotations(experiment_id)
        if ann.evidence_level is EvidenceLevel.CONCLUSION
        and ann.target_type is AnnotationTargetType.GENE
        and isinstance(ann.value, dict)
    }

    candidates_by_protein = _fused_candidates_by_protein(
        repo.list_fused_candidates(experiment_id),
        protein_ids={protein.protein_id for protein in proteins},
        top_k=top_k,
    )
    candidate_rows = [
        candidate for candidates in candidates_by_protein.values() for candidate in candidates
    ]
    unresolved_reasons: dict[str, int] = {}
    _count_unresolved(
        unresolved_reasons,
        "no_candidate_neighbors",
        sum(1 for protein in proteins if protein.protein_id not in candidates_by_protein),
    )
    if not candidate_rows:
        summary = _empty_summary(experiment_id, proteins=len(proteins))
        summary["unresolved_reasons"] = unresolved_reasons
        return summary

    neighbor_accessions = sorted({candidate.target_id for candidate in candidate_rows})
    gene_by_acc = resolver.resolve(neighbor_accessions) if neighbor_accessions else {}
    neighbor_genes = sorted({gene for gene in gene_by_acc.values() if gene})
    disease_by_gene = diseases.fetch(neighbor_genes) if neighbor_genes else {}

    annotations: dict[str, MetaAnnotation] = {}
    proteins_with_hypotheses = 0
    for protein in proteins:
        candidates = candidates_by_protein.get(protein.protein_id, [])
        support: dict[str, dict[str, Any]] = {}
        for candidate in candidates:
            gene = gene_by_acc.get(candidate.target_id)
            if not gene:
                _count_unresolved(unresolved_reasons, "unresolved_gene")
                continue
            facts = disease_by_gene.get(gene, [])
            if not facts:
                _count_unresolved(unresolved_reasons, "no_ctd_disease")
                continue
            for fact in facts:
                if (protein.gene, fact.disease_id) in concluded:
                    continue
                entry = support.setdefault(
                    fact.disease_id,
                    {"disease_name": fact.disease_name, "neighbors": []},
                )
                entry["neighbors"].append(_support_row(candidate, gene, fact.relation_id))

        if support:
            proteins_with_hypotheses += 1
        for disease_id, entry in support.items():
            sup = sorted(
                entry["neighbors"],
                key=lambda row: (-row["fused_score"], row["fusion_rank"], row["accession"]),
            )
            value = {"disease_id": disease_id, "disease_name": entry["disease_name"]}
            attribute = f"disease:{disease_id}"
            annotation_id = stable_annotation_id(
                experiment_id=experiment_id,
                target_type=AnnotationTargetType.PROTEIN.value,
                target=protein.protein_id,
                attribute=attribute,
                value=value,
                source=_SOURCE,
            )
            annotations[annotation_id] = MetaAnnotation(
                annotation_id=annotation_id,
                experiment_id=experiment_id,
                target=protein.protein_id,
                target_type=AnnotationTargetType.PROTEIN,
                attribute=attribute,
                value=value,
                evidence_level=EvidenceLevel.HYPOTHESIS,
                source=_SOURCE,
                derivation={
                    "neighbors": sup,
                    "via_genes": sorted({row["gene"] for row in sup}),
                    "confidence": max(row["score"] for row in sup),
                    "fused_confidence": max(row["fused_score"] for row in sup),
                    "support_count": len(sup),
                    "support_channels": sorted(
                        {channel for row in sup for channel in row["support_channels"]}
                    ),
                    "ranking": "fused_candidate",
                    "candidate_source": "fused_candidate",
                },
                provenance={
                    "neighbor_source": "fused_candidate",
                    "ctd_version": diseases.version,
                },
            )

    rows = [annotations[key] for key in sorted(annotations)]
    written = repo.add_annotations(rows) if rows else 0
    return {
        "experiment_id": experiment_id,
        "proteins": len(proteins),
        "proteins_with_hypotheses": proteins_with_hypotheses,
        "candidate_neighbors": len(candidate_rows),
        "hypotheses": len(rows),
        "written": written,
        "source": _SOURCE,
        "unresolved_reasons": dict(sorted(unresolved_reasons.items())),
    }


def _fused_candidates_by_protein(
    candidates: list[FusedCandidate],
    *,
    protein_ids: set[str],
    top_k: int | None,
) -> dict[str, list[FusedCandidate]]:
    out: dict[str, list[FusedCandidate]] = {}
    for candidate in candidates:
        if candidate.query_protein_id not in protein_ids:
            continue
        if candidate.target_type.lower() != "protein":
            continue
        if candidate.relation_type != "CANDIDATE_NEIGHBOR":
            continue
        if top_k is not None and candidate.fusion_rank > top_k:
            continue
        out.setdefault(candidate.query_protein_id, []).append(candidate)
    for protein_id, rows in list(out.items()):
        out[protein_id] = sorted(
            rows,
            key=lambda row: (row.fusion_rank, -row.fused_score, row.target_id),
        )
    return out


def _support_row(candidate: FusedCandidate, gene: str, ctd_relation_id: str) -> dict[str, Any]:
    channel_evidence = list(candidate.meta.get("channel_evidence", []))
    best = _best_channel_summary(channel_evidence)
    return {
        "accession": candidate.target_id,
        "gene": gene,
        "fused_score": candidate.fused_score,
        "fusion_rank": candidate.fusion_rank,
        "support_channels": list(candidate.support_channels),
        "evidence_ids": list(candidate.evidence_ids),
        "candidate_id": candidate.candidate_id,
        "ctd_relation_id": ctd_relation_id,
        "score": best["score"],
        "coverage": best.get("coverage"),
        "taxon_id": best.get("taxon_id"),
        "channel_evidence": channel_evidence,
    }


def _best_channel_summary(channel_evidence: list[dict[str, Any]]) -> dict[str, Any]:
    if not channel_evidence:
        return {"score": 0.0}
    structure_rows = [row for row in channel_evidence if row.get("channel") == "structure"]
    rows = structure_rows or channel_evidence
    best = max(rows, key=lambda row: float(row.get("score") or 0.0))
    meta = best.get("meta") if isinstance(best.get("meta"), dict) else {}
    return {
        "score": float(best.get("score") or 0.0),
        "coverage": meta.get("coverage"),
        "taxon_id": meta.get("taxon_id"),
    }


def _count_unresolved(reasons: dict[str, int], reason: str, count: int = 1) -> None:
    if count <= 0:
        return
    reasons[reason] = reasons.get(reason, 0) + count


def _empty_summary(experiment_id: str, *, proteins: int) -> dict[str, Any]:
    return {
        "experiment_id": experiment_id,
        "proteins": proteins,
        "proteins_with_hypotheses": 0,
        "candidate_neighbors": 0,
        "hypotheses": 0,
        "written": 0,
        "source": _SOURCE,
        "unresolved_reasons": {},
    }


__all__ = ["generate_experiment_hypotheses"]
