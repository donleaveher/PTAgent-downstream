"""Neighbor provider contracts for multi-source protein candidate fusion."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class NeighborCandidate:
    """One channel-specific protein neighbor candidate."""

    query_accession: str
    target_accession: str
    channel: str
    rank: int
    score: float
    evidence_id: str = ""
    provider: str = ""
    provider_version: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NeighborProviderResult:
    """Unified output from an evidence-backed neighbor provider.

    `candidates` are consumed by fusion. `runs`, `evidence`, and `statuses`
    are persisted by the application service when the repository supports the
    concrete row types. Providers stay free of database writes.
    """

    candidates: list[NeighborCandidate] = field(default_factory=list)
    runs: list[Any] = field(default_factory=list)
    evidence: list[Any] = field(default_factory=list)
    statuses: list[Any] = field(default_factory=list)
    empty_queries: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def by_query(self) -> dict[str, list[NeighborCandidate]]:
        grouped: dict[str, list[NeighborCandidate]] = {
            query: [] for query in sorted(set(self.empty_queries))
        }
        for candidate in self.candidates:
            grouped.setdefault(candidate.query_accession, []).append(candidate)
        for query, rows in list(grouped.items()):
            grouped[query] = sorted(
                rows,
                key=lambda row: (row.rank, -row.score, row.target_accession),
            )
        return grouped

    # Backward-compatible map-like helpers for older tests/callers.
    def __getitem__(self, query_accession: str) -> list[NeighborCandidate]:
        return self.by_query()[query_accession]

    def values(self):
        return self.by_query().values()

    def __eq__(self, other: object) -> bool:
        if isinstance(other, dict):
            return self.by_query() == other
        return super().__eq__(other)


@runtime_checkable
class NeighborProvider(Protocol):
    provider_id: str
    channel: str
    name: str
    version: str

    def search(
        self, accessions: list[str], *, top_k: int | None = None
    ) -> NeighborProviderResult:
        """Return candidates plus optional evidence/run/status rows."""

        ...


NeighborProviderFactory = Callable[..., NeighborProvider]


class NeighborProviderRegistry:
    """Name-to-provider factory registry used by application orchestration."""

    def __init__(self) -> None:
        self._factories: dict[str, NeighborProviderFactory] = {}

    def register(
        self, provider_id: str, factory: NeighborProviderFactory
    ) -> "NeighborProviderRegistry":
        if not provider_id.strip():
            raise ValueError("provider_id must be non-empty")
        self._factories[provider_id] = factory
        return self

    def create(self, provider_id: str, **kwargs: Any) -> NeighborProvider:
        try:
            factory = self._factories[provider_id]
        except KeyError as exc:
            raise ValueError(f"unknown neighbor provider: {provider_id}") from exc
        return factory(**kwargs)

    def provider_ids(self) -> list[str]:
        return sorted(self._factories)


__all__ = [
    "NeighborCandidate",
    "NeighborProvider",
    "NeighborProviderFactory",
    "NeighborProviderRegistry",
    "NeighborProviderResult",
]
