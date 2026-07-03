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
from pkg.structure.catalog import StructureCatalogRecord, StructureStatus
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


class _MissingStructure:
    name = "Foldseek-AlphaFold"
    version = "afdb-2024_01"

    def __init__(self) -> None:
        self.last_structure_records: dict[str, StructureCatalogRecord] = {}

    def search(self, accessions: list[str], *, top_k: int | None = None):
        self.last_structure_records = {
            acc: StructureCatalogRecord(
                accession=acc,
                raw_accession=acc,
                source="AlphaFoldDB",
                source_version=self.version,
                status=StructureStatus.MISSING,
                reason="not_found_in_catalog",
                provenance={"source_form": "plain"},
            )
            for acc in accessions
        }
        return {acc: [] for acc in accessions}


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

    runs = repo.list_structure_search_runs("exp_1")
    assert len(runs) == 1
    assert runs[0].provider == "Foldseek-AlphaFold"
    assert runs[0].status == "completed"
    evidence = repo.list_structure_neighbor_evidence("exp_1")
    assert len(evidence) == 1
    assert evidence[0].run_id == runs[0].run_id
    assert evidence[0].query_protein_id == "prot_2"
    assert evidence[0].query_accession == "Q_NOVEL"
    assert evidence[0].target_accession == "P_HUMAN"
    assert evidence[0].score == 0.9


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


def test_missing_structure_status_is_persisted_without_hypothesis() -> None:
    repo = InMemoryExperimentRepository()
    ingest_experiment_payload(_payload_with_novel_protein(), repo)
    structure = _MissingStructure()

    result = generate_experiment_hypotheses(
        "exp_1",
        repository=repo,
        structure_provider=structure,
        gene_resolver=InMemoryGeneResolver({}),
        disease_source=_FakeCTD({}),
    )

    assert result["hypotheses"] == 0
    statuses = repo.list_structure_statuses("exp_1")
    by_protein = {row.protein_id: row for row in statuses}
    assert set(by_protein) == {"prot_1", "prot_2"}
    assert by_protein["prot_2"].raw_accession == "Q_NOVEL"
    assert by_protein["prot_2"].status == "missing"
    assert by_protein["prot_2"].reason == "not_found_in_catalog"
    assert by_protein["prot_2"].provider == "AlphaFoldDB"
    runs = repo.list_structure_search_runs("exp_1")
    assert len(runs) == 1
    assert runs[0].status == "skipped_no_query_structures"
    assert repo.list_structure_neighbor_evidence("exp_1") == []


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


def test_supporting_neighbors_are_reranked_by_rrf_fusion() -> None:
    repo = InMemoryExperimentRepository()
    ingest_experiment_payload(_payload_with_novel_protein(), repo)
    # 一个蛋白的 3 个结构近邻经 3 个基因都指向同一疾病；纯 score 序 N_A 居首，
    # 但 N_B 覆盖度最高 → RRF 融合后 N_B 顶到首位（confidence 仍取最高结构分，保持兼容）。
    structure = _FakeStructure(
        {
            "Q_NOVEL": [
                StructuralNeighbor("Q_NOVEL", "N_A", score=0.9, coverage=0.10, taxon_id=9606),
                StructuralNeighbor("Q_NOVEL", "N_B", score=0.8, coverage=0.99, taxon_id=9606),
                StructuralNeighbor("Q_NOVEL", "N_C", score=0.7, coverage=0.98, taxon_id=9606),
            ]
        }
    )
    resolver = InMemoryGeneResolver({"N_A": "GA", "N_B": "GB", "N_C": "GC"})
    ctd = _FakeCTD(
        {
            "GA": [GeneDiseaseFact("GA", "MESH:D1", "DX", "marker", "rA")],
            "GB": [GeneDiseaseFact("GB", "MESH:D1", "DX", "marker", "rB")],
            "GC": [GeneDiseaseFact("GC", "MESH:D1", "DX", "marker", "rC")],
        }
    )

    generate_experiment_hypotheses(
        "exp_1", repository=repo, structure_provider=structure, gene_resolver=resolver, disease_source=ctd
    )
    der = repo.list_annotations("exp_1")[0].derivation
    assert der["neighbors"][0]["accession"] == "N_B"      # 重排把高覆盖近邻顶上来
    assert der["neighbors"][0]["coverage"] == 0.99
    assert der["confidence"] == 0.9                         # 最高结构分(N_A)，与顺序无关
    assert der["ranking"] == "rrf(score,coverage)"
    assert der["rerank_confidence"] == max(n["fused_score"] for n in der["neighbors"])

    # 关掉重排 → 回到纯 score 序（N_A 居首）
    repo2 = InMemoryExperimentRepository()
    ingest_experiment_payload(_payload_with_novel_protein(), repo2)
    generate_experiment_hypotheses(
        "exp_1", repository=repo2, structure_provider=structure, gene_resolver=resolver,
        disease_source=ctd, rerank=False,
    )
    der2 = repo2.list_annotations("exp_1")[0].derivation
    assert der2["neighbors"][0]["accession"] == "N_A"
    assert der2["ranking"] == "score"


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
