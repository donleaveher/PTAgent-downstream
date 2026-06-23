"""M3：结构近邻借 CTD 疾病 → 蛋白级假说。"""

from __future__ import annotations

import pytest

from application.knowledge import generate_experiment_hypotheses
from pkg.disease import GeneDiseaseFact, InMemoryGeneResolver
from pkg.experiment import (
    AnnotationTargetType,
    EvidenceLevel,
    InMemoryExperimentRepository,
    MetaAnnotation,
    ingest_experiment_payload,
)
from pkg.structure import StructuralNeighbor
from tests.pkg.test_experiment_models import valid_payload


def _payload_with_novel_protein() -> dict:
    payload = valid_payload()
    payload["proteins"].append(
        {"protein_id": "prot_2", "accession": "Q_NOVEL", "gene": "Novelx", "peptide_ids": []}
    )
    return payload


class _FakeStructure:
    name = "Foldseek-AlphaFold"
    version = "afdb-2024_01"

    def __init__(self, mapping: dict[str, list[StructuralNeighbor]]) -> None:
        self.mapping = mapping
        self.calls: list[list[str]] = []

    def search(self, accessions: list[str], *, top_k: int | None = None):
        self.calls.append(list(accessions))
        return {acc: self.mapping.get(acc, []) for acc in accessions}


class _FakeCTD:
    name = "CTD"
    version = "2026_03"

    def __init__(self, mapping: dict[str, list[GeneDiseaseFact]]) -> None:
        self.mapping = mapping

    def fetch(self, genes: list[str]) -> dict[str, list[GeneDiseaseFact]]:
        return {g: self.mapping[g] for g in genes if g in self.mapping}


_INFLAMMATION = GeneDiseaseFact(
    gene="HUMANG",
    disease_id="MESH:D007249",
    disease_name="Inflammation",
    evidence_type="marker/mechanism",
    relation_id="9999|MESH:D007249",
)


def _deps():
    structure = _FakeStructure(
        {"Q_NOVEL": [StructuralNeighbor("Q_NOVEL", "P_HUMAN", score=0.9, coverage=0.95, taxon_id=9606)]}
    )
    resolver = InMemoryGeneResolver({"P_HUMAN": "HUMANG"})
    ctd = _FakeCTD({"HUMANG": [_INFLAMMATION]})
    return structure, resolver, ctd


def test_structural_neighbor_borrows_ctd_disease_as_protein_hypothesis() -> None:
    repo = InMemoryExperimentRepository()
    ingest_experiment_payload(_payload_with_novel_protein(), repo)
    structure, resolver, ctd = _deps()

    result = generate_experiment_hypotheses(
        "exp_1",
        repository=repo,
        structure_provider=structure,
        gene_resolver=resolver,
        disease_source=ctd,
    )

    assert structure.calls == [["P12345", "Q_NOVEL"]]  # 去重+排序的全部蛋白 accession
    assert result["hypotheses"] == 1
    assert result["proteins_with_hypotheses"] == 1

    anns = repo.list_annotations("exp_1")
    assert len(anns) == 1
    hyp = anns[0]
    assert hyp.target == "prot_2"  # 假说挂在大鼠蛋白上
    assert hyp.target_type is AnnotationTargetType.PROTEIN
    assert hyp.evidence_level is EvidenceLevel.HYPOTHESIS
    assert hyp.source == "Foldseek-KNN"
    assert hyp.attribute == "disease:MESH:D007249"
    assert hyp.derivation["via_genes"] == ["HUMANG"]
    assert hyp.derivation["confidence"] == 0.9
    assert hyp.derivation["neighbors"][0]["accession"] == "P_HUMAN"
    assert hyp.derivation["neighbors"][0]["taxon_id"] == 9606  # 跨物种：大鼠→人


def test_no_hypothesis_when_protein_gene_already_concluded() -> None:
    repo = InMemoryExperimentRepository()
    ingest_experiment_payload(_payload_with_novel_protein(), repo)
    structure, resolver, ctd = _deps()
    # prot_2 的基因 Novelx 已对同一疾病有 CTD 直接结论 → 不应再出假说
    repo.add_annotations(
        [
            MetaAnnotation(
                experiment_id="exp_1",
                target="Novelx",
                target_type=AnnotationTargetType.GENE,
                attribute="disease:MESH:D007249",
                value={"disease_id": "MESH:D007249", "disease_name": "Inflammation"},
                evidence_level=EvidenceLevel.CONCLUSION,
                source="CTD",
            )
        ]
    )

    result = generate_experiment_hypotheses(
        "exp_1",
        repository=repo,
        structure_provider=structure,
        gene_resolver=resolver,
        disease_source=ctd,
    )
    assert result["hypotheses"] == 0


def test_hypotheses_are_idempotent() -> None:
    repo = InMemoryExperimentRepository()
    ingest_experiment_payload(_payload_with_novel_protein(), repo)
    structure, resolver, ctd = _deps()
    generate_experiment_hypotheses(
        "exp_1", repository=repo, structure_provider=structure, gene_resolver=resolver, disease_source=ctd
    )
    first = [a.annotation_id for a in repo.list_annotations("exp_1")]
    generate_experiment_hypotheses(
        "exp_1", repository=repo, structure_provider=structure, gene_resolver=resolver, disease_source=ctd
    )
    second = [a.annotation_id for a in repo.list_annotations("exp_1")]
    assert first == second and len(second) == 1


def test_unknown_experiment_rejected() -> None:
    structure, resolver, ctd = _deps()
    with pytest.raises(ValueError, match="unknown experiment_id"):
        generate_experiment_hypotheses(
            "missing",
            repository=InMemoryExperimentRepository(),
            structure_provider=structure,
            gene_resolver=resolver,
            disease_source=ctd,
        )
