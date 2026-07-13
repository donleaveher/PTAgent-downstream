"""Structure-channel implementations of the generic NeighborProvider contract."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from pkg.experiment import (
    ExperimentRepository,
    StructureEvidenceStatus,
    StructureNeighborEvidence,
    StructureSearchRun,
)
from pkg.retrieval.neighbors import (
    NeighborCandidate,
    NeighborProvider,
    NeighborProviderResult,
)
from pkg.retrieval.persistence import NeighborPersistenceContext, ProviderPersistenceAdapter
from pkg.structure.foldseek import get_structure_search_provider
from pkg.structure.types import StructureSearchProvider


class StructureEvidenceNeighborProvider(NeighborProvider):
    """`NeighborProvider` implementation for precomputed structure evidence."""

    channel = "structure"
    provider_id = "structure.evidence"
    name = "StructureEvidence"
    version = "structure-evidence-v1"

    def __init__(self, repository: ExperimentRepository, experiment_id: str) -> None:
        self._repo = repository
        self._experiment_id = experiment_id

    def search(
        self, accessions: list[str], *, top_k: int | None = None
    ) -> NeighborProviderResult:
        wanted = {accession for accession in accessions if accession}
        candidates: list[NeighborCandidate] = []
        empty_queries: set[str] = set(wanted)
        runs = {
            row.run_id: row
            for row in self._repo.list_structure_search_runs(self._experiment_id)
        }
        for row in self._repo.list_structure_neighbor_evidence(self._experiment_id):
            if row.query_accession not in wanted:
                continue
            empty_queries.discard(row.query_accession)
            run = runs.get(row.run_id)
            candidates.append(
                NeighborCandidate(
                    query_accession=row.query_accession,
                    target_accession=row.target_accession,
                    channel=self.channel,
                    rank=max(row.rank, 1),
                    score=row.score,
                    evidence_id=row.evidence_id,
                    provider=run.provider if run is not None else "structure_neighbor_evidence",
                    provider_version=run.provider_version if run is not None else "",
                    meta={
                        "coverage": row.coverage,
                        "taxon_id": row.taxon_id,
                        "taxon_name": row.taxon_name,
                        "run_id": row.run_id,
                        "relation_id": row.relation_id,
                        "source": "structure_neighbor_evidence",
                    },
                )
            )
        ranked = sorted(candidates, key=lambda item: (item.query_accession, item.rank, -item.score))
        if top_k is not None:
            by_query: dict[str, list[NeighborCandidate]] = defaultdict(list)
            for candidate in ranked:
                if len(by_query[candidate.query_accession]) < top_k:
                    by_query[candidate.query_accession].append(candidate)
            ranked = [candidate for rows in by_query.values() for candidate in rows]
        return NeighborProviderResult(
            candidates=ranked,
            empty_queries=sorted(empty_queries),
            meta={"provider_id": self.provider_id},
        )


class StructureSearchNeighborProvider(NeighborProvider):
    """`NeighborProvider` implementation for live structure search.

    The wrapped `StructureSearchProvider` (Foldseek/AlphaFold today) is adapted
    into the generic neighbor-provider architecture by returning
    `NeighborProviderResult(candidates, runs, evidence, statuses)`.
    """

    channel = "structure"
    provider_id = "structure.foldseek"
    name = "StructureSearch"

    def __init__(
        self,
        repository: ExperimentRepository,
        experiment_id: str,
        structure_provider: StructureSearchProvider | None = None,
    ) -> None:
        self._repo = repository
        self._experiment_id = experiment_id
        self._structure_provider = structure_provider
        self.version = getattr(structure_provider, "version", "")

    def search(
        self, accessions: list[str], *, top_k: int | None = None
    ) -> NeighborProviderResult:
        wanted = set(accessions)
        proteins = [
            protein
            for protein in self._repo.list_proteins(self._experiment_id)
            if protein.accession in wanted
        ]
        if not proteins:
            return NeighborProviderResult(empty_queries=sorted(wanted))
        provider = self._structure_provider or get_structure_search_provider()
        search_run, evidence_rows, status_rows = collect_structure_search_artifacts(
            experiment_id=self._experiment_id,
            proteins=proteins,
            structure_provider=provider,
            top_k=top_k,
        )
        candidates = structure_evidence_candidates(evidence_rows, search_run)
        empty_queries = sorted(
            wanted - {candidate.query_accession for candidate in candidates}
        )
        return NeighborProviderResult(
            candidates=candidates,
            runs=[search_run],
            evidence=evidence_rows,
            statuses=status_rows,
            empty_queries=empty_queries,
            meta={"provider_id": self.provider_id},
        )


class StructureEvidencePersistenceAdapter(ProviderPersistenceAdapter):
    """Persists structure-specific rows carried by `NeighborProviderResult`."""

    adapter_id = "structure.evidence"

    def persist(
        self,
        repository: ExperimentRepository,
        result: NeighborProviderResult,
        context: NeighborPersistenceContext,
    ) -> dict[str, int]:
        persisted: dict[str, int] = {}
        structure_statuses = [
            row for row in result.statuses if isinstance(row, StructureEvidenceStatus)
        ]
        if structure_statuses:
            persisted["structure_statuses"] = repository.add_structure_statuses(
                structure_statuses
            )

        structure_runs = [
            row for row in result.runs if isinstance(row, StructureSearchRun)
        ]
        for run in structure_runs:
            repository.save_structure_search_run(run)
        if structure_runs:
            persisted["structure_search_runs"] = len(structure_runs)

        structure_evidence = [
            row for row in result.evidence if isinstance(row, StructureNeighborEvidence)
        ]
        if structure_evidence:
            persisted["structure_neighbor_evidence"] = (
                repository.add_structure_neighbor_evidence(structure_evidence)
            )
        return persisted


def collect_structure_search_artifacts(
    *,
    experiment_id: str,
    proteins: list[Any],
    structure_provider: StructureSearchProvider,
    top_k: int | None = None,
) -> tuple[StructureSearchRun, list[StructureNeighborEvidence], list[StructureEvidenceStatus]]:
    """Run a structure provider and build repository rows without persisting."""

    query_accessions = sorted({protein.accession for protein in proteins})
    neighbors_by_acc = structure_provider.search(query_accessions, top_k=top_k)
    status_rows = _structure_status_rows(
        experiment_id=experiment_id,
        proteins=proteins,
        records=getattr(structure_provider, "last_structure_records", {}),
        provider_name=getattr(structure_provider, "name", "structure"),
    )
    search_run, neighbor_evidence = _structure_evidence_rows(
        experiment_id=experiment_id,
        proteins=proteins,
        neighbors_by_acc=neighbors_by_acc,
        provider_name=getattr(structure_provider, "name", "structure"),
        provider_version=getattr(structure_provider, "version", ""),
        top_k=top_k,
        structure_status_records=getattr(structure_provider, "last_structure_records", {}),
    )
    return search_run, neighbor_evidence, status_rows


def structure_evidence_candidates(
    evidence_rows: list[StructureNeighborEvidence],
    run: StructureSearchRun,
) -> list[NeighborCandidate]:
    return [
        NeighborCandidate(
            query_accession=row.query_accession,
            target_accession=row.target_accession,
            channel="structure",
            rank=max(row.rank, 1),
            score=row.score,
            evidence_id=row.evidence_id,
            provider=run.provider,
            provider_version=run.provider_version,
            meta={
                "coverage": row.coverage,
                "taxon_id": row.taxon_id,
                "taxon_name": row.taxon_name,
                "run_id": row.run_id,
                "relation_id": row.relation_id,
                "source": "structure_search_provider",
            },
        )
        for row in evidence_rows
    ]


def _structure_status_rows(
    *,
    experiment_id: str,
    proteins: list[Any],
    records: dict[str, Any],
    provider_name: str,
) -> list[StructureEvidenceStatus]:
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
    query_accessions = sorted({protein.accession for protein in proteins})
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

    protein_by_acc = {protein.accession: protein for protein in proteins}
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


__all__ = [
    "StructureEvidencePersistenceAdapter",
    "StructureEvidenceNeighborProvider",
    "StructureSearchNeighborProvider",
    "collect_structure_search_artifacts",
    "structure_evidence_candidates",
]
