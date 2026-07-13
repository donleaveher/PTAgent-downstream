"""Provider-driven neighbor search orchestration and RRF fusion."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from pkg.experiment import (
    ExperimentRepository,
    FusedCandidate,
    ProteinRecord,
    get_experiment_store,
)
from pkg.retrieval import (
    NeighborCandidate,
    NeighborEvidencePersistenceAdapter,
    NeighborPersistenceContext,
    NeighborProvider,
    NeighborProviderRegistry,
    NeighborProviderResult,
    ProviderPersistenceAdapter,
    rrf,
)
from pkg.retrieval.providers import (
    DomainNeighborProvider,
    SequenceNeighborProvider,
    StructureEvidencePersistenceAdapter,
    StructureEvidenceNeighborProvider,
    StructureSearchNeighborProvider,
)
from pkg.structure import StructureSearchProvider


def default_neighbor_provider_registry() -> NeighborProviderRegistry:
    registry = NeighborProviderRegistry()
    registry.register(
        "structure.foldseek",
        lambda **kwargs: StructureSearchNeighborProvider(
            kwargs["repository"],
            kwargs["experiment_id"],
            kwargs.get("structure_provider"),
        ),
    )
    registry.register(
        "structure.default",
        lambda **kwargs: StructureSearchNeighborProvider(
            kwargs["repository"],
            kwargs["experiment_id"],
            kwargs.get("structure_provider"),
        ),
    )
    registry.register(
        "structure.evidence",
        lambda **kwargs: StructureEvidenceNeighborProvider(
            kwargs["repository"], kwargs["experiment_id"]
        ),
    )
    registry.register("sequence.kmer", _sequence_kmer_provider_factory)
    registry.register("domain.interpro", _domain_interpro_provider_factory)
    return registry


def default_neighbor_persistence_adapters() -> list[ProviderPersistenceAdapter]:
    return [
        NeighborEvidencePersistenceAdapter(),
        StructureEvidencePersistenceAdapter(),
    ]


def build_neighbor_providers(
    provider_names: Sequence[str],
    *,
    repository: ExperimentRepository,
    experiment_id: str,
    structure_provider: StructureSearchProvider | None = None,
    provider_options: dict[str, dict[str, Any]] | None = None,
    registry: NeighborProviderRegistry | None = None,
) -> list[NeighborProvider]:
    reg = registry or default_neighbor_provider_registry()
    options_by_name = provider_options or {}
    return [
        reg.create(
            provider_name,
            repository=repository,
            experiment_id=experiment_id,
            structure_provider=structure_provider,
            options=options_by_name.get(provider_name, {}),
        )
        for provider_name in provider_names
    ]


def run_neighbor_search(
    experiment_id: str,
    *,
    repository: ExperimentRepository | None = None,
    providers: Sequence[NeighborProvider] = (),
    provider_names: Sequence[str] | None = None,
    provider_registry: NeighborProviderRegistry | None = None,
    provider_options: dict[str, dict[str, Any]] | None = None,
    structure_provider: StructureSearchProvider | None = None,
    persistence_adapters: Sequence[ProviderPersistenceAdapter] | None = None,
    protein_ids: list[str] | None = None,
    top_k: int = 20,
    rrf_k: int = 60,
) -> dict[str, Any]:
    """Run neighbor providers, fuse ranked candidates, and persist rows."""

    if top_k < 1:
        raise ValueError("top_k must be positive")
    if rrf_k < 1:
        raise ValueError("rrf_k must be positive")

    repo = repository or get_experiment_store()
    context = repo.get_context(experiment_id)
    if context is None:
        raise ValueError(f"unknown experiment_id: {experiment_id}")

    proteins = repo.list_proteins(experiment_id)
    if protein_ids is not None:
        selected = set(protein_ids)
        proteins = [protein for protein in proteins if protein.protein_id in selected]
    if not proteins:
        return {
            "experiment_id": experiment_id,
            "query_proteins": 0,
            "fused_candidates": 0,
            "channels": {},
            "providers": [],
        }

    protein_by_accession = {protein.accession: protein for protein in proteins}
    query_accessions = sorted(protein_by_accession)

    provider_list = list(providers)
    if provider_names is not None:
        provider_list = [
            *build_neighbor_providers(
                provider_names,
                repository=repo,
                experiment_id=experiment_id,
                structure_provider=structure_provider,
                provider_options=provider_options,
                registry=provider_registry,
            ),
            *provider_list,
        ]
    persistence_adapter_list = (
        default_neighbor_persistence_adapters()
        if persistence_adapters is None
        else list(persistence_adapters)
    )

    by_query_channel: dict[str, dict[str, list[NeighborCandidate]]] = defaultdict(dict)
    channel_counts: dict[str, int] = {}
    provider_ids: list[str] = []
    provider_errors: dict[str, str] = {}
    persisted: dict[str, int] = {}

    for provider in provider_list:
        provider_name = getattr(provider, "provider_id", "") or getattr(
            provider, "name", provider.__class__.__name__
        )
        provider_ids.append(provider_name)
        started_at = datetime.now(timezone.utc)
        try:
            result = _normalize_provider_result(provider.search(query_accessions, top_k=top_k))
        except Exception as exc:
            provider_errors[provider_name] = f"{type(exc).__name__}: {exc}"
            continue
        finished_at = datetime.now(timezone.utc)
        persistence_context = _persistence_context(
            provider=provider,
            provider_id=provider_name,
            result=result,
            experiment_id=experiment_id,
            query_accessions=query_accessions,
            query_protein_ids={
                protein.accession: protein.protein_id for protein in proteins
            },
            top_k=top_k,
            started_at=started_at,
            finished_at=finished_at,
        )
        _persist_provider_result(
            repo, result, persistence_context, persistence_adapter_list, persisted
        )
        rows = result.candidates
        _add_channel_candidates(by_query_channel, rows)
        if rows:
            channel = getattr(provider, "channel", rows[0].channel)
            channel_counts[channel] = channel_counts.get(channel, 0) + len(rows)

    fused_rows: list[FusedCandidate] = []
    for accession in query_accessions:
        protein = protein_by_accession[accession]
        channels = by_query_channel.get(accession, {})
        if not channels:
            continue
        fused_rows.extend(
            _fuse_query_candidates(
                experiment_id=experiment_id,
                protein=protein,
                channels=channels,
                top_k=top_k,
                rrf_k=rrf_k,
            )
        )

    written = repo.add_fused_candidates(fused_rows) if fused_rows else 0
    return {
        "experiment_id": experiment_id,
        "query_proteins": len(proteins),
        "fused_candidates": written,
        "channels": dict(sorted(channel_counts.items())),
        "providers": provider_ids,
        "provider_errors": provider_errors,
        "persisted": dict(sorted(persisted.items())),
    }


def generate_fused_neighbor_candidates(
    experiment_id: str,
    *,
    repository: ExperimentRepository | None = None,
    protein_ids: list[str] | None = None,
    sequence_provider: NeighborProvider | None = None,
    providers: Sequence[NeighborProvider] | None = None,
    provider_names: Sequence[str] | None = None,
    provider_options: dict[str, dict[str, Any]] | None = None,
    persistence_adapters: Sequence[ProviderPersistenceAdapter] | None = None,
    top_k: int = 20,
    rrf_k: int = 60,
) -> dict[str, Any]:
    """Compatibility wrapper for the old neighbor-fusion entry point."""

    repo = repository or get_experiment_store()
    provider_list = list(providers) if providers is not None else [
        StructureEvidenceNeighborProvider(repo, experiment_id)
    ]
    if sequence_provider is not None:
        provider_list.append(sequence_provider)
    return run_neighbor_search(
        experiment_id,
        repository=repo,
        providers=provider_list,
        provider_names=provider_names,
        provider_options=provider_options,
        persistence_adapters=persistence_adapters,
        protein_ids=protein_ids,
        top_k=top_k,
        rrf_k=rrf_k,
    )


def _add_channel_candidates(
    by_query_channel: dict[str, dict[str, list[NeighborCandidate]]],
    candidates: list[NeighborCandidate],
) -> None:
    for candidate in candidates:
        if candidate.target_accession == candidate.query_accession:
            continue
        by_query_channel[candidate.query_accession].setdefault(candidate.channel, []).append(
            candidate
        )
    for channels in by_query_channel.values():
        for channel, rows in channels.items():
            channels[channel] = sorted(
                rows,
                key=lambda row: (row.rank, -row.score, row.target_accession),
            )


def _normalize_provider_result(result: Any) -> NeighborProviderResult:
    if isinstance(result, NeighborProviderResult):
        return result
    if isinstance(result, dict):
        return NeighborProviderResult(
            candidates=[candidate for rows in result.values() for candidate in rows],
            empty_queries=[query for query, rows in result.items() if not rows],
        )
    raise TypeError(f"unsupported neighbor provider result: {type(result).__name__}")


def _persist_provider_result(
    repo: ExperimentRepository,
    result: NeighborProviderResult,
    context: NeighborPersistenceContext,
    adapters: Sequence[ProviderPersistenceAdapter],
    persisted: dict[str, int],
) -> None:
    for adapter in adapters:
        for key, count in adapter.persist(repo, result, context).items():
            persisted[key] = persisted.get(key, 0) + count


def _persistence_context(
    *,
    provider: NeighborProvider,
    provider_id: str,
    result: NeighborProviderResult,
    experiment_id: str,
    query_accessions: list[str],
    query_protein_ids: dict[str, str],
    top_k: int,
    started_at: datetime,
    finished_at: datetime,
) -> NeighborPersistenceContext:
    native_run = result.runs[0] if result.runs else None
    first_candidate = result.candidates[0] if result.candidates else None
    channel = (
        getattr(provider, "channel", "")
        or (first_candidate.channel if first_candidate is not None else "")
        or "unknown"
    )
    provider_label = (
        (first_candidate.provider if first_candidate is not None else "")
        or getattr(native_run, "provider", "")
        or getattr(provider, "name", provider.__class__.__name__)
    )
    provider_version = (
        (first_candidate.provider_version if first_candidate is not None else "")
        or getattr(native_run, "provider_version", "")
        or getattr(provider, "version", "")
        or ""
    )
    status = getattr(native_run, "status", "") or (
        "completed" if result.candidates else "no_neighbors"
    )
    return NeighborPersistenceContext(
        experiment_id=experiment_id,
        provider_id=provider_id,
        provider=provider_label,
        provider_version=provider_version,
        channel=channel,
        query_accessions=tuple(query_accessions),
        query_protein_ids=query_protein_ids,
        top_k=top_k,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        meta={
            "provider_class": provider.__class__.__name__,
            "result_meta": result.meta,
        },
    )


def _sequence_kmer_provider_factory(**kwargs: Any) -> SequenceNeighborProvider:
    options = dict(kwargs.get("options") or {})
    sequences = options.pop("sequences", None)
    if not isinstance(sequences, dict):
        raise ValueError("sequence.kmer provider requires options['sequences']")
    return SequenceNeighborProvider(sequences, **options)


def _domain_interpro_provider_factory(**kwargs: Any) -> DomainNeighborProvider:
    options = dict(kwargs.get("options") or {})
    domains = options.pop("domains", None)
    if not isinstance(domains, dict):
        raise ValueError("domain.interpro provider requires options['domains']")
    return DomainNeighborProvider(domains, **options)


def _fuse_query_candidates(
    *,
    experiment_id: str,
    protein: ProteinRecord,
    channels: dict[str, list[NeighborCandidate]],
    top_k: int,
    rrf_k: int,
) -> list[FusedCandidate]:
    ranked_lists = [
        [candidate.target_accession for candidate in candidates]
        for _channel, candidates in sorted(channels.items())
        if candidates
    ]
    fused = rrf(ranked_lists, k=rrf_k, top_n=top_k)
    candidates_by_target: dict[str, list[NeighborCandidate]] = defaultdict(list)
    for candidates in channels.values():
        for candidate in candidates:
            candidates_by_target[candidate.target_accession].append(candidate)

    rows: list[FusedCandidate] = []
    for fusion_rank, (target, fused_score) in enumerate(fused, start=1):
        support = sorted({row.channel for row in candidates_by_target[target]})
        evidence_ids = sorted(
            {row.evidence_id for row in candidates_by_target[target] if row.evidence_id}
        )
        payload = {
            "experiment_id": experiment_id,
            "query_protein_id": protein.protein_id,
            "target_type": "protein",
            "target_id": target,
            "relation_type": "CANDIDATE_NEIGHBOR",
        }
        rows.append(
            FusedCandidate(
                candidate_id=f"fc_{_stable_hash(payload)[:32]}",
                experiment_id=experiment_id,
                query_protein_id=protein.protein_id,
                query_accession=protein.accession,
                target_type="protein",
                target_id=target,
                relation_type="CANDIDATE_NEIGHBOR",
                fused_score=fused_score,
                fusion_rank=fusion_rank,
                support_channels=support,
                evidence_ids=evidence_ids,
                meta={
                    "fusion": "rrf",
                    "rrf_k": rrf_k,
                    "channel_evidence": [
                        {
                            "channel": row.channel,
                            "target_accession": row.target_accession,
                            "rank": row.rank,
                            "score": row.score,
                            "evidence_id": row.evidence_id,
                            "provider": row.provider,
                            "provider_version": row.provider_version,
                            "meta": row.meta,
                        }
                        for row in sorted(
                            candidates_by_target[target],
                            key=lambda item: (item.channel, item.rank, item.target_accession),
                        )
                    ],
                },
            )
        )
    return rows


def _stable_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "StructureEvidenceNeighborProvider",
    "StructureSearchNeighborProvider",
    "build_neighbor_providers",
    "default_neighbor_persistence_adapters",
    "default_neighbor_provider_registry",
    "generate_fused_neighbor_candidates",
    "run_neighbor_search",
]
