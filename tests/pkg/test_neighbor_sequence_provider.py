from __future__ import annotations

from pkg.retrieval import SequenceNeighborProvider as PublicSequenceNeighborProvider
from pkg.retrieval.providers import SequenceNeighborProvider


def test_sequence_neighbor_provider_public_export_points_to_concrete_provider() -> None:
    assert PublicSequenceNeighborProvider is SequenceNeighborProvider


def test_sequence_neighbor_provider_ranks_similar_sequences_and_excludes_self() -> None:
    provider = SequenceNeighborProvider(
        {
            "Q": "MPEPTIDEKAAAA",
            "H": "MPEPTIDERAAAA",
            "FAR": "ZZZZZZZZZZZZ",
        },
        version="seq-test",
        top_k=5,
    )

    out = provider.search(["Q"])["Q"]

    assert [row.target_accession for row in out] == ["H"]
    assert out[0].query_accession == "Q"
    assert out[0].channel == "sequence"
    assert out[0].rank == 1
    assert out[0].score > 0
    assert out[0].evidence_id.startswith("seq_")
    assert out[0].provider == "Sequence-Kmer"
    assert out[0].provider_version == "seq-test"


def test_sequence_neighbor_provider_returns_empty_for_missing_query_sequence() -> None:
    provider = SequenceNeighborProvider({"A": "AAAAAA"})

    assert provider.search(["UNKNOWN"]) == {"UNKNOWN": []}
