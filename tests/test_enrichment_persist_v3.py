"""§4.3 富集结果持久化：服务把全量富集写入仓库，带 checksum、可幂等重跑。"""
from __future__ import annotations

from application.analysis import run_disease_enrichment
from pkg.experiment import (
    AnnotationTargetType,
    DifferentialDirection,
    DifferentialResult,
    EvidenceLevel,
    InMemoryExperimentRepository,
    MetaAnnotation,
    ingest_experiment_payload,
)

EXP = "exp_enr"


def _payload() -> dict:
    return {
        "context": {"experiment_id": EXP, "raw_text": "x"},
        "groups": [{"group_id": "g1", "label": "L1", "role": "case"}],
        "proteins": [
            {"protein_id": f"prot_{i}", "accession": f"P{i}", "gene": f"G{i}", "peptide_ids": []}
            for i in range(1, 21)  # 背景 G1..G20
        ],
        "peptides": [],
    }


def _seed() -> InMemoryExperimentRepository:
    repo = InMemoryExperimentRepository()
    ingest_experiment_payload(_payload(), repo)  # 背景 G1..G5
    repo.add_annotations(
        [
            MetaAnnotation(
                experiment_id=EXP,
                target=g,
                target_type=AnnotationTargetType.GENE,
                attribute="disease:MESH:DX",
                value={"disease_id": "MESH:DX", "disease_name": "Disease X"},
                evidence_level=EvidenceLevel.CONCLUSION,
                source="CTD",
                provenance={"db_version": "2026_03"},
            )
            for g in ("G1", "G2", "G3")
        ]
    )
    repo.add_differentials(
        [
            DifferentialResult(
                experiment_id=EXP,
                protein_id=pid,
                case_group_id="g1",
                control_group_id="g0",
                log2fc=2.0,
                direction=DifferentialDirection.UP,
                is_differential=True,
            )
            for pid in ("prot_1", "prot_2", "prot_3")  # 差异基因 G1,G2,G3 全落在疾病集
        ]
    )
    return repo


def test_enrichment_results_are_persisted_with_provenance() -> None:
    repo = _seed()
    summary = run_disease_enrichment(EXP, repository=repo, min_overlap=1)

    assert summary["written"] == 1
    assert summary["gene_set_version"] == "2026_03"
    assert summary["study_checksum"] and summary["background_checksum"]

    stored = repo.list_enrichments(EXP)
    assert len(stored) == 1
    rec = stored[0]
    assert rec.term == "MESH:DX" and rec.term_name == "Disease X"
    assert rec.overlap == 3 and rec.term_size == 3
    assert rec.study_size == 3 and rec.background_size == 20
    assert rec.is_significant is True
    assert rec.gene_set_source == "CTD" and rec.gene_set_version == "2026_03"
    assert rec.study_checksum == summary["study_checksum"]
    assert rec.background_checksum == summary["background_checksum"]
    assert rec.meta["overlap_genes"] == ["G1", "G2", "G3"]


def test_persist_is_idempotent_on_rerun() -> None:
    repo = _seed()
    run_disease_enrichment(EXP, repository=repo, min_overlap=1)
    run_disease_enrichment(EXP, repository=repo, min_overlap=1)
    # 同一 (experiment, term_type, term) 幂等覆盖，不堆叠
    assert len(repo.list_enrichments(EXP)) == 1


def test_persist_false_skips_writes() -> None:
    repo = _seed()
    summary = run_disease_enrichment(EXP, repository=repo, min_overlap=1, persist=False)
    assert summary["written"] == 0
    assert repo.list_enrichments(EXP) == []


def test_full_results_persisted_not_only_significant() -> None:
    repo = _seed()
    # 高阈值不影响"写全量"：非显著项也入库，只是 is_significant=False
    summary = run_disease_enrichment(EXP, repository=repo, min_overlap=1, q_threshold=0.0)
    assert summary["enriched"] == 0           # 没有项达到 q<=0（显著计数）
    assert len(repo.list_enrichments(EXP)) == 1  # 但全量结果仍落库
    assert repo.list_enrichments(EXP)[0].is_significant is False
