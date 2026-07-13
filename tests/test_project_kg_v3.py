"""L3 投影服务测试：MySQL 事实 → 两层知识图谱（对内存仓库 + 内存图库）。

覆盖：双节点缝合（Q3）、两层分离（Q4）、边带 evidence_level/log2fc/score、
跨基因缝合走到疾病、幂等可重投、删工作区不动通用 KG（阶段验收）。
"""
from __future__ import annotations

import pytest

from application.graph.project_kg import project_experiment_kg
from pkg.experiment import (
    AnnotationTargetType,
    DifferentialDirection,
    DifferentialResult,
    EvidenceLevel,
    ExperimentBundle,
    ExperimentContext,
    ExperimentGroup,
    FusedCandidate,
    GroupRole,
    InMemoryExperimentRepository,
    MetaAnnotation,
    NeighborEvidence,
    NeighborSearchRun,
    ProteinRecord,
    StructureNeighborEvidence,
    StructureSearchRun,
)
from pkg.graph import (
    EdgeType,
    GraphScope,
    InMemoryGraphStore,
    NodeLabel,
    NodeRef,
)

EXP = "exp_kg_test"


def _seed_repo() -> InMemoryExperimentRepository:
    repo = InMemoryExperimentRepository()
    repo.save_bundle(
        ExperimentBundle(
            context=ExperimentContext(experiment_id=EXP, raw_text="background"),
            groups=[
                ExperimentGroup(group_id="case", label="Case", role=GroupRole.CASE),
                ExperimentGroup(group_id="ctrl", label="Control", role=GroupRole.CONTROL),
            ],
            proteins=[
                ProteinRecord(
                    protein_id="prot1",
                    accession="P1",
                    gene="Stat3",
                    organism="Rattus norvegicus",
                    taxon_id=10116,
                ),
                ProteinRecord(
                    protein_id="prot2",
                    accession="P2",
                    gene="Casp3",
                    organism="Rattus norvegicus",
                    taxon_id=10116,
                ),
            ],
            peptides=[],
        )
    )
    repo.add_annotations(
        [
            MetaAnnotation(  # CTD 基因结论（通用 KG）
                experiment_id=EXP,
                target="Stat3",
                target_type=AnnotationTargetType.GENE,
                attribute="disease:MESH:D001",
                value={"disease_id": "MESH:D001", "disease_name": "Brain Ischemia"},
                evidence_level=EvidenceLevel.CONCLUSION,
                source="CTD",
            ),
            MetaAnnotation(  # 结构类比蛋白级假说（实验工作区），target = protein_id
                experiment_id=EXP,
                target="prot2",
                target_type=AnnotationTargetType.PROTEIN,
                attribute="disease:MESH:D002",
                value={"disease_id": "MESH:D002", "disease_name": "Inflammation"},
                evidence_level=EvidenceLevel.HYPOTHESIS,
                source="Foldseek-KNN",
            ),
        ]
    )
    repo.add_differentials(
        [
            DifferentialResult(
                experiment_id=EXP,
                protein_id="prot1",
                case_group_id="case",
                control_group_id="ctrl",
                log2fc=2.0,
                direction=DifferentialDirection.UP,
                is_differential=True,
            ),
            DifferentialResult(
                experiment_id=EXP,
                protein_id="prot2",
                case_group_id="case",
                control_group_id="ctrl",
                log2fc=-1.5,
                direction=DifferentialDirection.DOWN,
                is_differential=True,
            ),
        ]
    )
    repo.save_structure_search_run(
        StructureSearchRun(
            run_id="strun_kg",
            experiment_id=EXP,
            provider="Foldseek-AlphaFold",
            provider_version="afdb-2024_01",
            db_version="afdb-2024_01",
            params_hash="a" * 64,
            params={"top_k": 20},
            status="completed",
            meta={"neighbor_count": 1},
        )
    )
    repo.add_structure_neighbor_evidence(
        [
            StructureNeighborEvidence(
                evidence_id="sne_high",
                run_id="strun_kg",
                experiment_id=EXP,
                query_protein_id="prot2",
                query_accession="P2",
                target_accession="P9",
                score=0.95,
                coverage=0.8,
                rank=1,
                taxon_id=9606,
                relation_id="P2->P9",
            )
        ]
    )
    return repo


def test_projection_builds_two_layer_graph() -> None:
    repo = _seed_repo()
    store = InMemoryGraphStore()
    summary = project_experiment_kg(EXP, repository=repo, store=store)

    assert summary["nodes_by_label"] == {
        "Protein": 3,  # P1, P2 + 结构近邻引入的 P9
        "Gene": 2,
        "Disease": 2,
        "Group": 2,
        "Comparison": 1,
    }
    assert summary["edges_by_type"] == {
        "ENCODED_BY": 2,
        "ASSOCIATED_WITH": 2,  # 1 基因结论 + 1 蛋白假说
        "STRUCTURAL_NEIGHBOR": 1,
        "CANDIDATE_NEIGHBOR": 0,
        "DIFFERENTIAL": 0,
        "DIFFERENTIAL_IN": 2,
        "CASE_GROUP": 1,
        "CONTROL_GROUP": 1,
    }
    assert summary["general_nodes"] == 7
    assert summary["experiment_nodes"] == 3
    assert summary["structural_neighbors"] == 1
    assert summary["structure_neighbor_evidence"] == 1
    assert summary["fused_candidates"] == 0
    assert summary["candidate_neighbors"] == 0
    assert summary["projection_skipped"] == {}

    # 两层分离：分组节点 + 差异/假说边在实验工作区；其余在通用 KG
    assert store.count_nodes(scope=GraphScope.EXPERIMENT, experiment_id=EXP) == 3
    assert store.count_edges(scope=GraphScope.EXPERIMENT, experiment_id=EXP) == 5
    assert store.count_edges(scope=GraphScope.GENERAL) == 4

    # 节点回指 MySQL + 轻量属性
    p1 = store.get_node(NodeLabel.PROTEIN, "P1")
    assert p1 is not None and p1.mysql_ref == {"accession": "P1"}
    assert p1.properties["taxon_id"] == 10116
    case = store.get_node(NodeLabel.GROUP, f"{EXP}:case")
    assert case is not None and case.properties["role"] == "case"


def test_traversal_protein_to_disease_structure_and_group() -> None:
    repo = _seed_repo()
    store = InMemoryGraphStore()
    project_experiment_kg(EXP, repository=repo, store=store)

    # P1 → 基因 Stat3 结论 → 疾病（跨 ENCODED_BY 缝合）
    p1_diseases = store.protein_diseases("P1", experiment_id=EXP)
    assert [(d.disease_key, d.evidence_level, d.via) for d in p1_diseases] == [
        ("MESH:D001", "CONCLUSION", "gene:STAT3")
    ]

    # P2 → 蛋白级假说 → 疾病（实验工作区）
    p2_diseases = store.protein_diseases("P2", experiment_id=EXP)
    assert [(d.disease_key, d.evidence_level, d.via) for d in p2_diseases] == [
        ("MESH:D002", "HYPOTHESIS", "protein")
    ]

    # P2 → 结构近邻（跨物种桥，带 score）
    sn = store.neighbors(NodeRef(NodeLabel.PROTEIN, "P2"), EdgeType.STRUCTURAL_NEIGHBOR)
    assert len(sn) == 1
    assert sn[0].end.key == "P9" and sn[0].properties["score"] == 0.95
    assert sn[0].properties["source_relation_id"] == "P2->P9"
    assert "evidence_id" not in sn[0].properties
    assert sn[0].properties["projection_reason"] == "rank<=5"

    # P1 → 显式比较 → case/control 组（带 log2fc）
    diff = store.neighbors(
        NodeRef(NodeLabel.PROTEIN, "P1"),
        EdgeType.DIFFERENTIAL_IN,
        experiment_id=EXP,
    )
    assert len(diff) == 1
    assert diff[0].end.key == f"{EXP}:comparison:case:vs:ctrl"
    assert diff[0].properties["log2fc"] == 2.0
    comparison = diff[0].end
    assert [
        edge.end.key
        for edge in store.neighbors(
            comparison, EdgeType.CASE_GROUP, experiment_id=EXP
        )
    ] == [f"{EXP}:case"]
    assert [
        edge.end.key
        for edge in store.neighbors(
            comparison, EdgeType.CONTROL_GROUP, experiment_id=EXP
        )
    ] == [f"{EXP}:ctrl"]


def test_projection_is_idempotent() -> None:
    repo = _seed_repo()
    store = InMemoryGraphStore()
    first = project_experiment_kg(EXP, repository=repo, store=store)
    project_experiment_kg(EXP, repository=repo, store=store)
    assert store.count_nodes() == first["nodes"] == 10
    assert store.count_edges() == first["edges"] == 9


def test_drop_experiment_keeps_general_kg() -> None:
    repo = _seed_repo()
    store = InMemoryGraphStore()
    project_experiment_kg(EXP, repository=repo, store=store)

    removed = store.drop_experiment(EXP)
    assert removed == 8  # 3 工作区节点 + 5 实验边

    assert store.count_nodes(scope=GraphScope.EXPERIMENT) == 0
    assert store.count_edges(scope=GraphScope.EXPERIMENT) == 0
    assert store.count_nodes(scope=GraphScope.GENERAL) == 7  # 通用 KG 不受影响
    assert store.count_edges(scope=GraphScope.GENERAL) == 4

    # 通用基因结论仍可达；本实验蛋白假说已随工作区清除
    assert {
        d.disease_key for d in store.protein_diseases("P1", experiment_id=EXP)
    } == {"MESH:D001"}
    assert store.protein_diseases("P2", experiment_id=EXP) == []


def test_projection_policy_skips_low_rank_structure_evidence() -> None:
    repo = _seed_repo()
    repo.add_structure_neighbor_evidence(
        [
            StructureNeighborEvidence(
                evidence_id="sne_low",
                run_id="strun_kg",
                experiment_id=EXP,
                query_protein_id="prot2",
                query_accession="P2",
                target_accession="P_LOW",
                score=0.9,
                coverage=0.9,
                rank=99,
                taxon_id=9606,
                relation_id="P2->P_LOW",
            )
        ]
    )
    store = InMemoryGraphStore()
    summary = project_experiment_kg(EXP, repository=repo, store=store)

    assert summary["structure_neighbor_evidence"] == 2
    assert summary["structural_neighbors"] == 1
    assert summary["projection_skipped"] == {"rank>5": 1}
    sn = store.neighbors(NodeRef(NodeLabel.PROTEIN, "P2"), EdgeType.STRUCTURAL_NEIGHBOR)
    assert [edge.end.key for edge in sn] == ["P9"]


def test_fused_candidate_projects_only_when_policy_significant() -> None:
    repo = _seed_repo()
    repo.save_neighbor_search_run(
        NeighborSearchRun(
            run_id="nrun_seq",
            experiment_id=EXP,
            provider_id="sequence.kmer",
            provider="Sequence-Kmer",
            channel="sequence",
            params_hash="b" * 64,
            status="completed",
        )
    )
    repo.add_neighbor_evidence(
        [
            NeighborEvidence(
                evidence_id="ne_seq_1",
                run_id="nrun_seq",
                experiment_id=EXP,
                query_protein_id="prot2",
                query_accession="P2",
                target_id="P9",
                relation_type="SEQUENCE_NEIGHBOR",
                channel="sequence",
                provider="Sequence-Kmer",
                rank=1,
                score=0.88,
                meta={"source_evidence_id": "seq_1"},
            ),
            NeighborEvidence(
                evidence_id="ne_seq_2",
                run_id="nrun_seq",
                experiment_id=EXP,
                query_protein_id="prot2",
                query_accession="P2",
                target_id="P_WEAK",
                relation_type="SEQUENCE_NEIGHBOR",
                channel="sequence",
                provider="Sequence-Kmer",
                rank=2,
                score=0.5,
                meta={"source_evidence_id": "seq_2"},
            ),
        ]
    )
    repo.add_fused_candidates(
        [
            FusedCandidate(
                candidate_id="fc_high",
                experiment_id=EXP,
                query_protein_id="prot2",
                query_accession="P2",
                target_type="protein",
                target_id="P9",
                relation_type="CANDIDATE_NEIGHBOR",
                fused_score=0.87,
                fusion_rank=1,
                support_channels=["structure", "sequence"],
                evidence_ids=["sne_high", "seq_1"],
            ),
            FusedCandidate(
                candidate_id="fc_weak",
                experiment_id=EXP,
                query_protein_id="prot2",
                query_accession="P2",
                target_type="protein",
                target_id="P_WEAK",
                relation_type="CANDIDATE_NEIGHBOR",
                fused_score=0.5,
                fusion_rank=8,
                support_channels=["sequence"],
                evidence_ids=["seq_2"],
            ),
        ]
    )
    store = InMemoryGraphStore()
    summary = project_experiment_kg(EXP, repository=repo, store=store)

    assert summary["fused_candidates"] == 2
    assert summary["candidate_neighbors"] == 1
    assert summary["projection_skipped"] == {
        "fusion_rank>5;support_channels<2": 1
    }
    edges = store.neighbors(
        NodeRef(NodeLabel.PROTEIN, "P2"),
        EdgeType.CANDIDATE_NEIGHBOR,
        experiment_id=EXP,
    )
    assert len(edges) == 1
    assert edges[0].scope is GraphScope.EXPERIMENT
    assert edges[0].end.key == "P9"
    assert edges[0].properties["candidate_id"] == "fc_high"
    assert edges[0].properties["support_channels"] == ["structure", "sequence"]
    assert edges[0].properties["projection_reason"] == (
        "fusion_rank<=5;support_channels>=2"
    )


def test_fused_candidate_rejects_missing_or_misaligned_evidence() -> None:
    repo = _seed_repo()
    repo.add_fused_candidates(
        [
            FusedCandidate(
                candidate_id="fc_invalid",
                experiment_id=EXP,
                query_protein_id="prot2",
                query_accession="P2",
                target_type="protein",
                target_id="P_OTHER",
                relation_type="CANDIDATE_NEIGHBOR",
                fused_score=0.8,
                fusion_rank=1,
                support_channels=["structure", "sequence"],
                evidence_ids=["sne_high", "missing_seq"],
            )
        ]
    )

    with pytest.raises(ValueError, match="does not match its query/target"):
        project_experiment_kg(EXP, repository=repo, store=InMemoryGraphStore())


def test_unknown_experiment_raises() -> None:
    store = InMemoryGraphStore()
    with pytest.raises(ValueError):
        project_experiment_kg("nope", repository=InMemoryExperimentRepository(), store=store)
