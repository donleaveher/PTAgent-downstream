from __future__ import annotations

import pytest

from pkg.graph import (
    canonical_gene_identity,
    canonical_protein_key,
    canonical_relation_key,
    normalize_gene_symbol,
)


def test_protein_identity_normalizes_common_accession_forms() -> None:
    assert canonical_protein_key("sp|P40763|STAT3_HUMAN") == "P40763"
    assert canonical_protein_key("P40763-2") == "P40763"
    assert canonical_protein_key("AF-P40763-F1-model_v6.cif.gz") == "P40763"


def test_gene_identity_is_case_insensitive_within_one_taxon() -> None:
    upper = canonical_gene_identity("STAT3", taxon_id=9606)
    mixed = canonical_gene_identity("Stat3", taxon_id=9606)
    assert upper == mixed
    assert upper.key == "taxon:9606|gene:STAT3"
    assert upper.properties["symbol"] == "STAT3"


def test_gene_identity_separates_same_symbol_across_taxa() -> None:
    human = canonical_gene_identity("STAT3", taxon_id=9606)
    rat = canonical_gene_identity("Stat3", taxon_id=10116)
    assert human.key != rat.key


def test_gene_identity_prefers_ncbi_gene_id() -> None:
    identity = canonical_gene_identity(
        "STAT3", taxon_id=9606, meta={"ncbi_gene_id": "6774"}
    )
    assert identity.key == "NCBIGene:6774"
    assert identity.ncbi_gene_id == "6774"


def test_empty_entity_identity_is_rejected() -> None:
    with pytest.raises(ValueError):
        canonical_protein_key("")
    with pytest.raises(ValueError):
        normalize_gene_symbol(" ")


def test_relation_identity_is_stable_and_versioned() -> None:
    first = canonical_relation_key("STRUCTURAL_NEIGHBOR", "P1", "P2", "Foldseek", "v1")
    same = canonical_relation_key("STRUCTURAL_NEIGHBOR", "P1", "P2", "Foldseek", "v1")
    changed = canonical_relation_key("STRUCTURAL_NEIGHBOR", "P1", "P2", "Foldseek", "v2")
    assert first == same
    assert first != changed
