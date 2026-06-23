"""CTD 全量基因疾病结论应用服务。"""

from __future__ import annotations

import pytest

from application.knowledge import annotate_experiment_diseases
from pkg.disease import GeneDiseaseFact
from pkg.experiment import (
    AnnotationTargetType,
    EvidenceLevel,
    InMemoryExperimentRepository,
    ingest_experiment_payload,
)
from tests.pkg.test_experiment_models import valid_payload


class _FakeDiseaseSource:
    name = "CTD"
    version = "2026_03"

    def __init__(self) -> None:
        self.requests: list[list[str]] = []

    def fetch(self, genes: list[str]) -> dict[str, list[GeneDiseaseFact]]:
        self.requests.append(genes)
        return {
            "Jak2": [
                GeneDiseaseFact(
                    gene="Jak2",
                    disease_id="MESH:D002545",
                    disease_name="Brain Ischemia",
                    evidence_type="marker/mechanism",
                    relation_id="3717|MESH:D002545",
                    pubmed_ids=("12345",),
                    provenance={"source_db": "CTD"},
                )
            ]
        }


def test_disease_annotation_targets_gene_with_conclusion() -> None:
    repo = InMemoryExperimentRepository()
    ingest_experiment_payload(valid_payload(), repo)
    source = _FakeDiseaseSource()

    result = annotate_experiment_diseases("exp_1", repository=repo, source=source)

    assert source.requests == [["Jak2"]]
    assert result["genes"] == 1
    assert result["genes_with_disease"] == 1
    assert result["genes_without_disease"] == []

    annotations = repo.list_annotations("exp_1")
    assert len(annotations) == 1
    ann = annotations[0]
    assert ann.target == "Jak2"
    assert ann.target_type is AnnotationTargetType.GENE
    assert ann.evidence_level is EvidenceLevel.CONCLUSION
    assert ann.source == "CTD"
    assert ann.attribute == "disease:MESH:D002545"
    assert ann.derivation["evidence_type"] == "marker/mechanism"
    assert ann.derivation["pubmed_ids"] == ["12345"]


def test_disease_annotation_is_idempotent() -> None:
    repo = InMemoryExperimentRepository()
    ingest_experiment_payload(valid_payload(), repo)
    source = _FakeDiseaseSource()
    annotate_experiment_diseases("exp_1", repository=repo, source=source)
    first = repo.list_annotations("exp_1")
    annotate_experiment_diseases("exp_1", repository=repo, source=source)
    second = repo.list_annotations("exp_1")
    assert [row.annotation_id for row in second] == [row.annotation_id for row in first]
    assert len(second) == 1


def test_disease_annotation_rejects_unknown_experiment() -> None:
    source = _FakeDiseaseSource()
    with pytest.raises(ValueError, match="unknown experiment_id"):
        annotate_experiment_diseases(
            "missing", repository=InMemoryExperimentRepository(), source=source
        )
    assert source.requests == []
