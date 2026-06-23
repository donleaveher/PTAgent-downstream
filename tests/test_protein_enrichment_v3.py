"""新版全量蛋白基础注释应用服务。"""

from __future__ import annotations

import pytest

from application.knowledge import enrich_experiment_proteins
from pkg.annotation import ProteinAnnotationFact
from pkg.experiment import EvidenceLevel, InMemoryExperimentRepository, ingest_experiment_payload
from tests.pkg.test_experiment_models import valid_payload


class _FakeSource:
    name = "UniProt-MCP"
    version = "2026_03"

    def __init__(self) -> None:
        self.requests: list[list[str]] = []

    def fetch(self, accessions: list[str]) -> dict[str, list[ProteinAnnotationFact]]:
        self.requests.append(accessions)
        return {
            "P12345": [
                ProteinAnnotationFact(
                    accession="P12345",
                    attribute="domain",
                    value="SH2",
                    source_ref="UniProt:P12345#domain",
                    provenance={"mcp_tool": "protein_annot", "db_version": self.version},
                ),
                ProteinAnnotationFact(
                    accession="P12345",
                    attribute="tissue",
                    value="brain",
                    evidence_code="ECO:0000269",
                ),
            ]
        }


def test_enriches_all_proteins_into_experiment_repository() -> None:
    payload = valid_payload()
    payload["proteins"].append(
        {
            "protein_id": "prot_2",
            "accession": "NO_HIT",
            "gene": "Unknown",
            "peptide_ids": [],
        }
    )
    repo = InMemoryExperimentRepository()
    ingest_experiment_payload(payload, repo)
    source = _FakeSource()

    result = enrich_experiment_proteins("exp_1", repository=repo, source=source)

    assert source.requests == [["NO_HIT", "P12345"]]
    assert result["proteins"] == 2
    assert result["proteins_with_facts"] == 1
    assert result["missing_accessions"] == ["NO_HIT"]
    annotations = repo.list_annotations("exp_1")
    assert len(annotations) == 2
    assert {row.attribute for row in annotations} == {"domain", "tissue"}
    assert all(row.evidence_level is EvidenceLevel.CONCLUSION for row in annotations)
    assert all(row.target == "prot_1" for row in annotations)
    tissue = next(row for row in annotations if row.attribute == "tissue")
    assert tissue.provenance["evidence_code"] == "ECO:0000269"


def test_enrichment_is_idempotent_by_stable_annotation_id() -> None:
    repo = InMemoryExperimentRepository()
    ingest_experiment_payload(valid_payload(), repo)
    source = _FakeSource()
    enrich_experiment_proteins("exp_1", repository=repo, source=source)
    first = repo.list_annotations("exp_1")
    enrich_experiment_proteins("exp_1", repository=repo, source=source)
    second = repo.list_annotations("exp_1")
    assert [row.annotation_id for row in second] == [row.annotation_id for row in first]
    assert len(second) == 2


def test_unknown_experiment_is_rejected_before_source_call() -> None:
    source = _FakeSource()
    with pytest.raises(ValueError, match="unknown experiment_id"):
        enrich_experiment_proteins(
            "missing",
            repository=InMemoryExperimentRepository(),
            source=source,
        )
    assert source.requests == []
