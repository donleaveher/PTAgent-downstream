"""Persistence contracts for neighbor provider results."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from typing import Protocol, runtime_checkable

from pkg.experiment import (
    ExperimentRepository,
    NeighborEvidence,
    NeighborEvidenceStatus,
    NeighborSearchRun,
)
from pkg.retrieval.neighbors import NeighborCandidate, NeighborProviderResult


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class NeighborPersistenceContext:
    """Provider execution context needed to persist generic neighbor evidence."""

    experiment_id: str
    provider_id: str
    provider: str
    provider_version: str
    channel: str
    query_accessions: tuple[str, ...]
    query_protein_ids: Mapping[str, str]
    top_k: int | None = None
    status: str = "completed"
    started_at: datetime = field(default_factory=_utcnow)
    finished_at: datetime = field(default_factory=_utcnow)
    params: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ProviderPersistenceAdapter(Protocol):
    """Persists provider-specific run/evidence/status rows."""

    adapter_id: str

    def persist(
        self,
        repository: ExperimentRepository,
        result: NeighborProviderResult,
        context: NeighborPersistenceContext,
    ) -> dict[str, int]:
        """Persist supported rows and return count deltas by summary key."""

        ...


class NeighborEvidencePersistenceAdapter(ProviderPersistenceAdapter):
    """Persists provider results into the generic neighbor evidence schema."""

    adapter_id = "neighbor.evidence"

    def persist(
        self,
        repository: ExperimentRepository,
        result: NeighborProviderResult,
        context: NeighborPersistenceContext,
    ) -> dict[str, int]:
        run = _neighbor_search_run(result, context)
        repository.save_neighbor_search_run(run)
        evidence_rows = [
            _neighbor_evidence_row(run, candidate, context)
            for candidate in result.candidates
        ]
        status_rows = _neighbor_status_rows(run, result, context)
        written_evidence = repository.add_neighbor_evidence(evidence_rows)
        written_statuses = repository.add_neighbor_statuses(status_rows)
        persisted = {"neighbor_search_runs": 1}
        if written_evidence:
            persisted["neighbor_evidence"] = written_evidence
        if written_statuses:
            persisted["neighbor_statuses"] = written_statuses
        return persisted


def _neighbor_search_run(
    result: NeighborProviderResult,
    context: NeighborPersistenceContext,
) -> NeighborSearchRun:
    params = {
        "experiment_id": context.experiment_id,
        "query_accessions": list(context.query_accessions),
        "top_k": context.top_k,
        "provider_id": context.provider_id,
        "provider_version": context.provider_version,
        **context.params,
    }
    params_hash = _stable_hash(params)
    native_run = _first_native_run(result)
    meta = dict(context.meta)
    if native_run is not None:
        meta.setdefault("native_run_id", getattr(native_run, "run_id", ""))
        meta.setdefault("native_status", getattr(native_run, "status", ""))
    meta.setdefault("candidate_count", len(result.candidates))
    meta.setdefault("empty_query_count", len(result.empty_queries))
    return NeighborSearchRun(
        run_id=f"nrun_{params_hash[:32]}",
        experiment_id=context.experiment_id,
        provider_id=context.provider_id,
        provider=context.provider,
        provider_version=context.provider_version,
        channel=context.channel,
        db_version=getattr(native_run, "db_version", "") if native_run is not None else "",
        params_hash=params_hash,
        params=params,
        status=context.status,
        started_at=context.started_at,
        finished_at=context.finished_at,
        meta=meta,
    )


def _neighbor_evidence_row(
    run: NeighborSearchRun,
    candidate: NeighborCandidate,
    context: NeighborPersistenceContext,
) -> NeighborEvidence:
    query_protein_id = context.query_protein_ids.get(candidate.query_accession, "")
    if not query_protein_id:
        raise ValueError(
            f"provider returned candidate for unknown query accession: "
            f"{candidate.query_accession}"
        )
    channel = candidate.channel or context.channel
    provider = candidate.provider or context.provider
    provider_version = candidate.provider_version or context.provider_version
    meta = dict(candidate.meta)
    meta.setdefault("provider_id", context.provider_id)
    if candidate.evidence_id:
        meta.setdefault("source_evidence_id", candidate.evidence_id)
    evidence_id = _stable_neighbor_evidence_id(
        run.run_id,
        candidate.query_accession,
        candidate.target_accession,
        channel,
    )
    return NeighborEvidence(
        evidence_id=evidence_id,
        run_id=run.run_id,
        experiment_id=context.experiment_id,
        query_protein_id=query_protein_id,
        query_accession=candidate.query_accession,
        target_type="protein",
        target_id=candidate.target_accession,
        relation_type=_relation_type(channel),
        channel=channel,
        provider=provider,
        provider_version=provider_version,
        rank=max(candidate.rank, 0),
        score=candidate.score,
        meta=meta,
        created_at=run.finished_at,
    )


def _neighbor_status_rows(
    run: NeighborSearchRun,
    result: NeighborProviderResult,
    context: NeighborPersistenceContext,
) -> list[NeighborEvidenceStatus]:
    rows: list[NeighborEvidenceStatus] = []
    covered_accessions: set[str] = set()
    for raw_status in result.statuses:
        row = _status_row_from_provider_status(run, raw_status, context)
        if row is None:
            continue
        covered_accessions.add(row.query_accession)
        rows.append(row)
    for accession in sorted(set(result.empty_queries) - covered_accessions):
        query_protein_id = context.query_protein_ids.get(accession, "")
        if not query_protein_id:
            continue
        rows.append(
            _status_row(
                run=run,
                context=context,
                query_protein_id=query_protein_id,
                query_accession=accession,
                status="no_neighbors",
                reason="provider_returned_no_candidates",
                meta={},
            )
        )
    return rows


def _status_row_from_provider_status(
    run: NeighborSearchRun,
    raw_status: Any,
    context: NeighborPersistenceContext,
) -> NeighborEvidenceStatus | None:
    protein_id = str(getattr(raw_status, "protein_id", "") or "")
    if not protein_id:
        return None
    query_accession = (
        str(getattr(raw_status, "normalized_accession", "") or "")
        or str(getattr(raw_status, "raw_accession", "") or "")
        or _accession_for_protein_id(context, protein_id)
    )
    if not query_accession:
        return None
    status = str(getattr(raw_status, "status", "") or "unresolved")
    reason = str(getattr(raw_status, "reason", "") or "")
    provider = str(getattr(raw_status, "provider", "") or context.provider)
    provider_version = str(
        getattr(raw_status, "provider_version", "") or context.provider_version
    )
    meta = _model_meta(raw_status)
    meta.setdefault("provider_id", context.provider_id)
    return _status_row(
        run=run,
        context=context,
        query_protein_id=protein_id,
        query_accession=query_accession,
        status=status,
        reason=reason,
        meta=meta,
        provider=provider,
        provider_version=provider_version,
    )


def _status_row(
    *,
    run: NeighborSearchRun,
    context: NeighborPersistenceContext,
    query_protein_id: str,
    query_accession: str,
    status: str,
    reason: str,
    meta: dict[str, Any],
    provider: str | None = None,
    provider_version: str | None = None,
) -> NeighborEvidenceStatus:
    payload = {
        "run_id": run.run_id,
        "query_protein_id": query_protein_id,
        "query_accession": query_accession,
        "channel": context.channel,
        "status": status,
        "reason": reason,
    }
    return NeighborEvidenceStatus(
        status_id=f"nes_{_stable_hash(payload)[:32]}",
        run_id=run.run_id,
        experiment_id=context.experiment_id,
        query_protein_id=query_protein_id,
        query_accession=query_accession,
        channel=context.channel,
        provider=provider or context.provider,
        provider_version=provider_version or context.provider_version,
        status=status,
        reason=reason,
        meta=meta,
        checked_at=run.finished_at,
    )


def _first_native_run(result: NeighborProviderResult) -> Any | None:
    return result.runs[0] if result.runs else None


def _accession_for_protein_id(
    context: NeighborPersistenceContext, protein_id: str
) -> str:
    for accession, mapped_protein_id in context.query_protein_ids.items():
        if mapped_protein_id == protein_id:
            return accession
    return ""


def _model_meta(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _relation_type(channel: str) -> str:
    if channel == "structure":
        return "STRUCTURAL_NEIGHBOR"
    return f"{channel.upper()}_NEIGHBOR"


def _stable_neighbor_evidence_id(
    run_id: str,
    query_accession: str,
    target_accession: str,
    channel: str,
) -> str:
    payload = {
        "run_id": run_id,
        "query_accession": query_accession,
        "target_accession": target_accession,
        "channel": channel,
    }
    return f"ne_{_stable_hash(payload)[:32]}"


def _stable_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "NeighborEvidencePersistenceAdapter",
    "NeighborPersistenceContext",
    "ProviderPersistenceAdapter",
]
