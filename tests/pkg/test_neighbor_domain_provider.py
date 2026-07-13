from __future__ import annotations

import pytest

from application.knowledge import build_neighbor_providers
from pkg.experiment import InMemoryExperimentRepository
from pkg.retrieval import DomainNeighborProvider as PublicDomainNeighborProvider
from pkg.retrieval.providers import DomainNeighborProvider


def test_domain_neighbor_provider_public_export_points_to_concrete_provider() -> None:
    assert PublicDomainNeighborProvider is DomainNeighborProvider


def test_domain_neighbor_provider_ranks_shared_domains_and_excludes_self() -> None:
    provider = DomainNeighborProvider(
        {
            "Q": ["IPR0001", "PF0002", "IPR0003"],
            "H": ["IPR0001", "PF0002", "IPR0003"],
            "PARTIAL": ["IPR0001"],
            "FAR": ["IPR9999"],
        },
        version="domain-test",
        top_k=5,
    )

    out = provider.search(["Q"])["Q"]

    assert [row.target_accession for row in out] == ["H", "PARTIAL"]
    assert out[0].query_accession == "Q"
    assert out[0].channel == "domain"
    assert out[0].rank == 1
    assert out[0].score == 1.0
    assert out[0].evidence_id.startswith("dom_")
    assert out[0].provider == "InterPro-Domain-Overlap"
    assert out[0].provider_version == "domain-test"
    assert out[1].score == pytest.approx(1 / 3)
    assert out[1].meta["shared_domain_ids"] == ["IPR0001"]


def test_domain_neighbor_provider_returns_empty_for_missing_or_unannotated_query() -> None:
    provider = DomainNeighborProvider({"A": []})

    assert provider.search(["A", "UNKNOWN"]) == {"A": [], "UNKNOWN": []}


def test_domain_provider_is_registered_and_requires_domain_assignments() -> None:
    providers = build_neighbor_providers(
        ("domain.interpro",),
        repository=InMemoryExperimentRepository(),
        experiment_id="exp_1",
        provider_options={
            "domain.interpro": {
                "domains": {"Q": ["IPR0001"], "H": ["IPR0001"]},
                "version": "registry-test",
            }
        },
    )

    assert len(providers) == 1
    assert isinstance(providers[0], DomainNeighborProvider)
    assert providers[0].version == "registry-test"

    with pytest.raises(ValueError, match=r"requires options\['domains'\]"):
        build_neighbor_providers(
            ("domain.interpro",),
            repository=InMemoryExperimentRepository(),
            experiment_id="exp_1",
        )
