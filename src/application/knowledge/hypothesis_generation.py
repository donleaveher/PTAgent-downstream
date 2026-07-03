"""结构近邻借 CTD 疾病 → 蛋白级假说（M3：把 M1 CTD 与 M2 Foldseek 接起来）。

对每个（差异）蛋白：取结构近邻(M2) → 解析近邻 gene → 查近邻 gene 的 CTD 疾病(M1)
→ 借过来生成 Protein 级 `MetaAnnotation(HYPOTHESIS)`。跨物种由结构近邻天然完成
（大鼠蛋白的近邻常含人源蛋白）。蛋白自身 gene 已有 CTD 直接结论的疾病不再出假说。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from pkg.disease import GeneDiseaseSource, GeneResolver, get_disease_source, get_gene_resolver
from pkg.experiment import (
    AnnotationTargetType,
    EvidenceLevel,
    ExperimentRepository,
    MetaAnnotation,
    StructureEvidenceStatus,
    StructureNeighborEvidence,
    StructureSearchRun,
    get_experiment_store,
    stable_annotation_id,
)
from pkg.structure import (
    StructureSearchProvider,
    get_structure_search_provider,
    rerank_neighbors,
)

_SOURCE = "Foldseek-KNN"


def generate_experiment_hypotheses(
    experiment_id: str,
    *,
    repository: ExperimentRepository | None = None,
    structure_provider: StructureSearchProvider | None = None,
    gene_resolver: GeneResolver | None = None,
    disease_source: GeneDiseaseSource | None = None,
    protein_ids: Iterable[str] | None = None,
    top_k: int | None = None,
    rerank: bool = True,
    rrf_k: int = 60,
) -> dict[str, Any]:
    """生成蛋白级结构类比假说，幂等落库。

    `protein_ids` 限定处理范围（L2 落地后传差异蛋白；默认全部蛋白）。
    """

    repo = repository or get_experiment_store()
    context = repo.get_context(experiment_id)
    if context is None:
        raise ValueError(f"unknown experiment_id: {experiment_id}")

    proteins = repo.list_proteins(experiment_id)
    if protein_ids is not None:
        wanted = set(protein_ids)
        proteins = [p for p in proteins if p.protein_id in wanted]
    if not proteins:
        return {
            "experiment_id": experiment_id,
            "proteins": 0,
            "proteins_with_hypotheses": 0,
            "hypotheses": 0,
            "written": 0,
            "source": _SOURCE,
        }

    structures = structure_provider or get_structure_search_provider()
    resolver = gene_resolver or get_gene_resolver()
    diseases = disease_source or get_disease_source()

    # 蛋白自身 gene 已有的 CTD 直接结论 (gene, disease_id) → 不重复出假说
    concluded = {
        (ann.target, ann.value.get("disease_id"))
        for ann in repo.list_annotations(experiment_id)
        if ann.evidence_level is EvidenceLevel.CONCLUSION
        and ann.target_type is AnnotationTargetType.GENE
        and isinstance(ann.value, dict)
    }

    # 1. 结构近邻（M2）
    query_accessions = sorted({p.accession for p in proteins})
    neighbors_by_acc = structures.search(query_accessions, top_k=top_k)
    structure_status_rows = _structure_status_rows(
        experiment_id=experiment_id,
        proteins=proteins,
        records=getattr(structures, "last_structure_records", {}),
        provider_name=getattr(structures, "name", "structure"),
    )
    if structure_status_rows:
        repo.add_structure_statuses(structure_status_rows)
    search_run, neighbor_evidence = _structure_evidence_rows(
        experiment_id=experiment_id,
        proteins=proteins,
        neighbors_by_acc=neighbors_by_acc,
        provider_name=getattr(structures, "name", "structure"),
        provider_version=getattr(structures, "version", ""),
        top_k=top_k,
        structure_status_records=getattr(structures, "last_structure_records", {}),
    )
    repo.save_structure_search_run(search_run)
    if neighbor_evidence:
        repo.add_structure_neighbor_evidence(neighbor_evidence)

    # 2. 近邻 accession → gene
    neighbor_accessions = sorted(
        {n.target_accession for ns in neighbors_by_acc.values() for n in ns}
    )
    gene_by_acc = resolver.resolve(neighbor_accessions) if neighbor_accessions else {}

    # 3. 近邻 gene → CTD 疾病（M1）
    neighbor_genes = sorted({g for g in gene_by_acc.values() if g})
    disease_by_gene = diseases.fetch(neighbor_genes) if neighbor_genes else {}

    # 4. 每蛋白聚合借来的疾病 → 蛋白级假说
    annotations: dict[str, MetaAnnotation] = {}
    proteins_with_hypotheses = 0
    for protein in proteins:
        prot_neighbors = neighbors_by_acc.get(protein.accession, [])
        # 多路融合重排（结构相似 + 覆盖度），把单路 score 升级为 RRF 融合分
        fused_by_acc = (
            {n.target_accession: fs for n, fs in rerank_neighbors(prot_neighbors, rrf_k=rrf_k)}
            if rerank
            else {}
        )
        support: dict[str, dict[str, Any]] = {}
        for neighbor in prot_neighbors:
            gene = gene_by_acc.get(neighbor.target_accession)
            if not gene:
                continue
            for fact in disease_by_gene.get(gene, []):
                if (protein.gene, fact.disease_id) in concluded:
                    continue  # 蛋白自身 gene 已有直接结论 → 不重复出假说
                entry = support.setdefault(
                    fact.disease_id,
                    {"disease_name": fact.disease_name, "neighbors": []},
                )
                entry["neighbors"].append(
                    {
                        "accession": neighbor.target_accession,
                        "gene": gene,
                        "score": neighbor.score,
                        "coverage": neighbor.coverage,
                        "taxon_id": neighbor.taxon_id,
                        "ctd_relation_id": fact.relation_id,
                        "fused_score": fused_by_acc.get(neighbor.target_accession, neighbor.score),
                    }
                )

        if support:
            proteins_with_hypotheses += 1
        for disease_id, entry in support.items():
            # 按融合分重排支持近邻（同分回退结构 score）
            sup = sorted(
                entry["neighbors"], key=lambda s: (s["fused_score"], s["score"]), reverse=True
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
                    "via_genes": sorted({s["gene"] for s in sup}),
                    "confidence": max(s["score"] for s in sup),  # 最高结构相似分（兼容）
                    "rerank_confidence": max(s["fused_score"] for s in sup),  # 融合重排最高分
                    "support_count": len(sup),
                    "ranking": "rrf(score,coverage)" if rerank else "score",
                },
                provenance={
                    "structure_version": structures.version,
                    "ctd_version": diseases.version,
                },
            )

    rows = [annotations[key] for key in sorted(annotations)]
    written = repo.add_annotations(rows)
    return {
        "experiment_id": experiment_id,
        "proteins": len(proteins),
        "proteins_with_hypotheses": proteins_with_hypotheses,
        "hypotheses": len(rows),
        "written": written,
        "source": _SOURCE,
    }


def _structure_status_rows(
    *,
    experiment_id: str,
    proteins: list[Any],
    records: dict[str, Any],
    provider_name: str,
) -> list[StructureEvidenceStatus]:
    """Convert provider structure resolution records into repository rows.

    Only non-available statuses are persisted here. Available structure records
    are already represented by Foldseek neighbors/provenance; missing and
    unusable records are the important audit trail for degradation.
    """

    if not records:
        return []
    rows: list[StructureEvidenceStatus] = []
    for protein in proteins:
        record = records.get(protein.accession)
        if record is None:
            continue
        raw_status = getattr(record, "status", "")
        status = str(getattr(raw_status, "value", raw_status))
        if status == "available":
            continue
        rows.append(
            StructureEvidenceStatus(
                experiment_id=experiment_id,
                protein_id=protein.protein_id,
                raw_accession=getattr(record, "raw_accession", "") or protein.accession,
                normalized_accession=getattr(record, "accession", "") or protein.accession,
                channel="structure",
                status=status or "missing",
                reason=getattr(record, "reason", "") or "structure_unavailable",
                provider=getattr(record, "source", "") or provider_name,
                provider_version=getattr(record, "source_version", ""),
                structure_id=getattr(record, "structure_id", ""),
                structure_format=getattr(record, "format", ""),
                local_path=getattr(record, "local_path", ""),
                object_uri=getattr(record, "object_uri", ""),
                sha256=getattr(record, "sha256", ""),
                meta=getattr(record, "provenance", {}) or {},
            )
        )
    return rows


def _structure_evidence_rows(
    *,
    experiment_id: str,
    proteins: list[Any],
    neighbors_by_acc: dict[str, list[Any]],
    provider_name: str,
    provider_version: str,
    top_k: int | None,
    structure_status_records: dict[str, Any],
) -> tuple[StructureSearchRun, list[StructureNeighborEvidence]]:
    query_accessions = sorted({p.accession for p in proteins})
    neighbor_count = sum(len(neighbors_by_acc.get(acc, [])) for acc in query_accessions)
    available_structures = sum(
        1
        for record in structure_status_records.values()
        if str(getattr(getattr(record, "status", ""), "value", getattr(record, "status", "")))
        == "available"
    )
    params = {
        "query_accessions": query_accessions,
        "top_k": top_k,
        "provider": provider_name,
        "provider_version": provider_version,
    }
    params_hash = _stable_hash(params)
    run_id = f"strun_{params_hash[:32]}"
    now = datetime.now(timezone.utc)
    status = "completed" if neighbor_count else "no_neighbors"
    if structure_status_records and available_structures == 0:
        status = "skipped_no_query_structures"

    run = StructureSearchRun(
        run_id=run_id,
        experiment_id=experiment_id,
        provider=provider_name,
        provider_version=provider_version,
        db_version=provider_version,
        params_hash=params_hash,
        params=params,
        status=status,
        started_at=now,
        finished_at=now,
        meta={
            "query_count": len(query_accessions),
            "neighbor_count": neighbor_count,
            "available_query_structures": available_structures,
        },
    )

    protein_by_acc = {p.accession: p for p in proteins}
    rows: list[StructureNeighborEvidence] = []
    for query_accession in query_accessions:
        protein = protein_by_acc[query_accession]
        for neighbor in neighbors_by_acc.get(query_accession, []):
            relation_id = (
                neighbor.relation_id
                or f"{neighbor.query_accession}|STRUCTURAL_NEIGHBOR|{neighbor.target_accession}"
            )
            evidence_payload = {
                "run_id": run_id,
                "experiment_id": experiment_id,
                "query_protein_id": protein.protein_id,
                "query_accession": neighbor.query_accession,
                "target_accession": neighbor.target_accession,
                "relation_id": relation_id,
            }
            rows.append(
                StructureNeighborEvidence(
                    evidence_id=f"sne_{_stable_hash(evidence_payload)[:32]}",
                    run_id=run_id,
                    experiment_id=experiment_id,
                    query_protein_id=protein.protein_id,
                    query_accession=neighbor.query_accession,
                    target_accession=neighbor.target_accession,
                    rank=neighbor.rank,
                    score=neighbor.score,
                    coverage=neighbor.coverage,
                    taxon_id=neighbor.taxon_id,
                    taxon_name=neighbor.taxon_name,
                    relation_id=relation_id,
                    provenance=neighbor.provenance,
                    created_at=now,
                )
            )
    return run, rows


def _stable_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = ["generate_experiment_hypotheses"]
