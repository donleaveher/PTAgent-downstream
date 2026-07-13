"""Sequence-channel implementations of the generic NeighborProvider contract."""

from __future__ import annotations

import hashlib
import json

from pkg.retrieval.neighbors import (
    NeighborCandidate,
    NeighborProvider,
    NeighborProviderResult,
)
from pkg.retrieval.recall import KmerIndex
from pkg.retrieval.rerank import seq_identity


class SequenceNeighborProvider(NeighborProvider):
    """`NeighborProvider` implementation for k-mer sequence similarity.

    Production can replace this with MMseqs2/BLAST while preserving the same
    `NeighborProviderResult` contract.
    """

    provider_id = "sequence.kmer"
    channel = "sequence"
    name = "Sequence-Kmer"

    def __init__(
        self,
        sequences: dict[str, str],
        *,
        version: str = "sequence-kmer-v1",
        top_k: int = 20,
        k_kmer: int = 3,
    ) -> None:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        self.version = version
        self._sequences = {
            str(acc).strip(): str(seq).strip().upper()
            for acc, seq in sequences.items()
            if str(acc).strip() and str(seq).strip()
        }
        self._top_k = top_k
        self._index = KmerIndex(self._sequences, k=k_kmer)
        self._k_kmer = k_kmer

    def search(
        self, accessions: list[str], *, top_k: int | None = None
    ) -> NeighborProviderResult:
        k = top_k if top_k is not None else self._top_k
        candidates: list[NeighborCandidate] = []
        empty_queries: list[str] = []
        for accession in sorted({str(acc).strip() for acc in accessions if str(acc).strip()}):
            if accession not in self._sequences:
                empty_queries.append(accession)
                continue
            query_sequence = self._sequences[accession]
            recalled = [
                target
                for target in self._index.recall(query_sequence, top_n=max(k * 5, k))
                if target != accession
            ]
            rows = sorted(
                (
                    (target, seq_identity(query_sequence, self._sequences[target]))
                    for target in recalled
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
                    evidence_id=_stable_sequence_evidence_id(accession, target, self.version),
                    provider=self.name,
                    provider_version=self.version,
                    meta={
                        "method": "kmer_hybrid",
                        "k_kmer": self._k_kmer,
                    },
                )
                for rank, (target, score) in enumerate(rows, start=1)
            )
        return NeighborProviderResult(
            candidates=candidates,
            empty_queries=empty_queries,
            meta={
                "provider_id": self.provider_id,
                "top_k": k,
                "k_kmer": self._k_kmer,
            },
        )


def _stable_sequence_evidence_id(
    query_accession: str, target_accession: str, version: str
) -> str:
    payload = {
        "channel": "sequence",
        "provider": SequenceNeighborProvider.name,
        "version": version,
        "query_accession": query_accession,
        "target_accession": target_accession,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"seq_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:32]}"


__all__ = ["SequenceNeighborProvider"]
