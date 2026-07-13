"""MVP 闭环验收：同一实验同时产出 CTD 直接 CONCLUSION 与 Foldseek 外推 HYPOTHESIS。

这是项目核心论点的端到端（假源）证明：
- 直接命中的蛋白 → 基因级结论；
- 未直接命中、但结构近邻（跨物种）有 CTD 关联的蛋白 → 蛋白级假说。
"""

from __future__ import annotations

from application.knowledge import (
    annotate_experiment_diseases,
    generate_experiment_hypotheses,
    run_neighbor_search,
)
from pkg.disease import GeneDiseaseFact, InMemoryGeneResolver
from pkg.experiment import (
    AnnotationTargetType,
    EvidenceLevel,
    InMemoryExperimentRepository,
    ingest_experiment_payload,
)
from pkg.retrieval.providers import StructureSearchNeighborProvider
from pkg.structure import StructuralNeighbor
from tests.pkg.test_experiment_models import valid_payload

_BRAIN_ISCHEMIA = GeneDiseaseFact(
    gene="Jak2",
    disease_id="MESH:D002545",
    disease_name="Brain Ischemia",
    evidence_type="marker/mechanism",
    relation_id="3717|MESH:D002545",
)
_INFLAMMATION = GeneDiseaseFact(
    gene="HUMANG",
    disease_id="MESH:D007249",
    disease_name="Inflammation",
    evidence_type="therapeutic",
    relation_id="9999|MESH:D007249",
)


class _FakeCTD:
    name = "CTD"
    version = "2026_03"

    def fetch(self, genes: list[str]) -> dict[str, list[GeneDiseaseFact]]:
        table = {"Jak2": [_BRAIN_ISCHEMIA], "HUMANG": [_INFLAMMATION]}
        return {g: table[g] for g in genes if g in table}


class _FakeStructure:
    name = "Foldseek-AlphaFold"
    version = "afdb-2024_01"

    def search(self, accessions: list[str], *, top_k: int | None = None):
        # 只有未直接命中的 prot_2 (Q_NOVEL) 有跨物种人源近邻
        mapping = {
            "Q_NOVEL": [StructuralNeighbor("Q_NOVEL", "P_HUMAN", score=0.93, coverage=0.9, taxon_id=9606)]
        }
        return {acc: mapping.get(acc, []) for acc in accessions}


def test_mvp_produces_both_conclusion_and_hypothesis() -> None:
    payload = valid_payload()  # prot_1 = Jak2（CTD 直接命中）
    payload["proteins"].append(
        {"protein_id": "prot_2", "accession": "Q_NOVEL", "gene": "Novelx", "peptide_ids": []}
    )
    repo = InMemoryExperimentRepository()
    ingest_experiment_payload(payload, repo)

    ctd = _FakeCTD()

    # 任务一/M1：全量基因 CTD 直接命中 → 结论
    conc = annotate_experiment_diseases("exp_1", repository=repo, source=ctd)
    # M2/M3：neighbor_search 内部运行结构 provider 并融合；hypothesis 只读 FusedCandidate。
    run_neighbor_search(
        "exp_1",
        repository=repo,
        providers=[StructureSearchNeighborProvider(repo, "exp_1", _FakeStructure())],
    )
    hyp = generate_experiment_hypotheses(
        "exp_1",
        repository=repo,
        gene_resolver=InMemoryGeneResolver({"P_HUMAN": "HUMANG"}),
        disease_source=ctd,
    )

    assert conc["annotations"] == 1
    assert hyp["hypotheses"] == 1

    anns = repo.list_annotations("exp_1")
    by_level = {a.evidence_level for a in anns}
    assert by_level == {EvidenceLevel.CONCLUSION, EvidenceLevel.HYPOTHESIS}

    conclusion = next(a for a in anns if a.evidence_level is EvidenceLevel.CONCLUSION)
    hypothesis = next(a for a in anns if a.evidence_level is EvidenceLevel.HYPOTHESIS)

    # 结论：基因级、来自 Jak2 自身 CTD 直接命中
    assert conclusion.target_type is AnnotationTargetType.GENE
    assert conclusion.target == "Jak2"
    assert conclusion.attribute == "disease:MESH:D002545"
    assert conclusion.source == "CTD"

    # 假说：蛋白级、跨物种结构类比（prot_2 借人源近邻的 CTD 疾病），可追溯
    assert hypothesis.target_type is AnnotationTargetType.PROTEIN
    assert hypothesis.target == "prot_2"
    assert hypothesis.attribute == "disease:MESH:D007249"
    assert hypothesis.source == "NeighborFusion"
    assert hypothesis.derivation["neighbors"][0]["taxon_id"] == 9606
    assert hypothesis.derivation["confidence"] == 0.93
