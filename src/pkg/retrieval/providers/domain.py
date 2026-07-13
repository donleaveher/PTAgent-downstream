"""Domain-overlap implementation of the generic NeighborProvider contract."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping

from pkg.retrieval.neighbors import (
    NeighborCandidate,
    NeighborProvider,
    NeighborProviderResult,
)
from pkg.retrieval.recall import jaccard


DomainValues = Iterable[str] | str | None


class DomainNeighborProvider(NeighborProvider):
    """Rank proteins by overlap of caller-supplied InterPro/Pfam domain IDs.

    This provider deliberately has no network dependency. The caller is
    responsible for obtaining domain assignments from InterPro, UniProt, or
    another source and for recording its source version in the version field.
    """

    provider_id = "domain.interpro"
    channel = "domain"
    name = "InterPro-Domain-Overlap"

    def __init__(
        self,
        domains: Mapping[str, DomainValues],
        *,
        version: str = "domain-interpro-v1",
        top_k: int = 20,
    ) -> None:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        self.version = version
        self._domains = {
            accession: domain_ids
            for raw_accession, raw_domains in domains.items()
            if (accession := str(raw_accession).strip())
            and (domain_ids := _normalize_domain_ids(raw_domains))
        }
        self._top_k = top_k

    def search(
        self, accessions: list[str], *, top_k: int | None = None
    ) -> NeighborProviderResult:
        k = top_k if top_k is not None else self._top_k
        candidates: list[NeighborCandidate] = []
        empty_queries: list[str] = []
        for accession in sorted({str(acc).strip() for acc in accessions if str(acc).strip()}):
            query_domains = self._domains.get(accession)
            if not query_domains:
                empty_queries.append(accession)
                continue
            rows = sorted(
                (
                    (
                        target,
                        jaccard(query_domains, target_domains),
                        sorted(query_domains & target_domains),
                        len(target_domains),
                    )
                    for target, target_domains in self._domains.items()
                    if target != accession and query_domains & target_domains
                ),
                key=lambda item: (-item[1], item[0]),
            )[:k]
            if not rows:
                empty_queries.append(accession)
            candidates.extend(
                NeighborCandidate(
                    query_accession=accession,
                    target_accession=target,
                    channel=self.channel,
                    rank=rank,
                    score=score,
                    evidence_id=_stable_domain_evidence_id(accession, target, self.version),
                    provider=self.name,
                    provider_version=self.version,
                    meta={
                        "method": "domain_jaccard",
                        "query_domain_count": len(query_domains),
                        "target_domain_count": target_domain_count,
                        "shared_domain_count": len(shared_domain_ids),
                        "shared_domain_ids": shared_domain_ids,
                    },
                )
                for rank, (target, score, shared_domain_ids, target_domain_count) in enumerate(
                    rows, start=1
                )
            )
        return NeighborProviderResult(
            candidates=candidates,
            empty_queries=empty_queries,
            meta={
                "provider_id": self.provider_id,
                "top_k": k,
                "domain_catalog_size": len(self._domains),
            },
        )


def _normalize_domain_ids(raw_domains: DomainValues) -> set[str]:
    if raw_domains is None:
        return set()
    values = (raw_domains,) if isinstance(raw_domains, str) else raw_domains
    return {str(domain).strip() for domain in values if str(domain).strip()}


def _stable_domain_evidence_id(
    query_accession: str, target_accession: str, version: str
) -> str:
    payload = {
        "channel": "domain",
        "provider": DomainNeighborProvider.name,
        "version": version,
        "query_accession": query_accession,
        "target_accession": target_accession,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"dom_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:32]}"


__all__ = ["DomainNeighborProvider"]
