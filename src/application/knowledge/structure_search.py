"""Persist structure-neighbor search evidence for later neighbor fusion."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pkg.experiment import ExperimentRepository, get_experiment_store
from pkg.retrieval.providers import collect_structure_search_artifacts
from pkg.structure import StructureSearchProvider, get_structure_search_provider


def run_structure_search(
    experiment_id: str,
    *,
    repository: ExperimentRepository | None = None,
    structure_provider: StructureSearchProvider | None = None,
    protein_ids: Iterable[str] | None = None,
    top_k: int | None = None,
) -> dict[str, Any]:
    """Run a structure provider and persist auditable structure evidence.

    This remains as an optional precompute/backfill entry point. The default
    downstream pipeline runs structure through the generic neighbor provider
    architecture instead.
    """

    repo = repository or get_experiment_store()
    context = repo.get_context(experiment_id)
    if context is None:
        raise ValueError(f"unknown experiment_id: {experiment_id}")

    proteins = repo.list_proteins(experiment_id)
    if protein_ids is not None:
        wanted = set(protein_ids)
        proteins = [protein for protein in proteins if protein.protein_id in wanted]
    if not proteins:
        return {
            "experiment_id": experiment_id,
            "query_proteins": 0,
            "structure_statuses": 0,
            "structure_search_runs": 0,
            "structure_neighbor_evidence": 0,
            "status": "no_query_proteins",
        }

    provider = structure_provider or get_structure_search_provider()
    search_run, neighbor_evidence, status_rows = collect_structure_search_artifacts(
        experiment_id=experiment_id,
        proteins=proteins,
        structure_provider=provider,
        top_k=top_k,
    )
    written_statuses = repo.add_structure_statuses(status_rows) if status_rows else 0
    repo.save_structure_search_run(search_run)
    written_evidence = (
        repo.add_structure_neighbor_evidence(neighbor_evidence) if neighbor_evidence else 0
    )

    return {
        "experiment_id": experiment_id,
        "query_proteins": len(proteins),
        "structure_statuses": written_statuses,
        "structure_search_runs": 1,
        "structure_neighbor_evidence": written_evidence,
        "status": search_run.status,
        "provider": search_run.provider,
        "provider_version": search_run.provider_version,
    }


__all__ = ["run_structure_search"]
