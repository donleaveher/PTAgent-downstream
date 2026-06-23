"""§10 分层报告测试：从冻结快照出可审计 Markdown，分层/可追溯/确定性/防篡改/只读。"""
from __future__ import annotations

import pytest

from application.analysis import run_disease_enrichment
from application.experiment.freeze import freeze_experiment
from application.knowledge.deep_search import verify_experiment_hypotheses
from application.report import generate_experiment_report
from pkg.deep_search import EvidenceRecord, EvidenceStance, InMemoryLiteratureSource
from pkg.experiment import (
    AnnotationTargetType,
    DifferentialDirection,
    DifferentialResult,
    EvidenceLevel,
    ExperimentBundle,
    ExperimentContext,
    ExperimentGroup,
    ExperimentSnapshot,
    GroupRole,
    InMemoryExperimentRepository,
    MetaAnnotation,
    ProteinRecord,
)

EXP = "exp_rep"


def _frozen_repo() -> InMemoryExperimentRepository:
    repo = InMemoryExperimentRepository()
    repo.save_bundle(
        ExperimentBundle(
            context=ExperimentContext(
                experiment_id=EXP,
                raw_text="ischemia",
                title="Jak2 CIRI",
                disease=["Brain Ischemia"],
                organism="rat",
                assay="LC-MS/MS",
            ),
            groups=[
                ExperimentGroup(group_id="case", label="Case", role=GroupRole.CASE),
                ExperimentGroup(group_id="ctrl", label="Control", role=GroupRole.CONTROL),
            ],
            proteins=[
                ProteinRecord(protein_id="prot1", accession="P1", gene="Stat3", taxon_id=10116),
                ProteinRecord(protein_id="prot2", accession="P2", gene="Casp3", taxon_id=10116),
            ],
            peptides=[],
        )
    )
    repo.add_annotations(
        [
            MetaAnnotation(  # 公共事实：CTD 基因结论
                annotation_id="ann_conc",
                experiment_id=EXP,
                target="Stat3",
                target_type=AnnotationTargetType.GENE,
                attribute="disease:D001",
                value={"disease_id": "D001", "disease_name": "Brain Ischemia"},
                evidence_level=EvidenceLevel.CONCLUSION,
                source="CTD",
                provenance={"db_version": "2026_03"},
            ),
            MetaAnnotation(  # 公共事实：UniProt 蛋白基础注释（附录）
                annotation_id="ann_base",
                experiment_id=EXP,
                target="prot1",
                target_type=AnnotationTargetType.PROTEIN,
                attribute="function:kinase",
                value={"name": "kinase activity"},
                evidence_level=EvidenceLevel.CONCLUSION,
                source="UniProt",
                provenance={"db_version": "2026_02"},
            ),
            MetaAnnotation(  # 推导假说 → deep-search 反驳 → 伪理
                annotation_id="ann_hypA",
                experiment_id=EXP,
                target="prot1",
                target_type=AnnotationTargetType.PROTEIN,
                attribute="disease:D002",
                value={"disease_id": "D002", "disease_name": "Sepsis"},
                evidence_level=EvidenceLevel.HYPOTHESIS,
                source="Foldseek-KNN",
                derivation={"via_genes": ["Aaa"], "confidence": 0.8},
            ),
            MetaAnnotation(  # 推导假说 → deep-search 无证据 → 未决
                annotation_id="ann_hypB",
                experiment_id=EXP,
                target="prot2",
                target_type=AnnotationTargetType.PROTEIN,
                attribute="disease:D003",
                value={"disease_id": "D003", "disease_name": "Fibrosis"},
                evidence_level=EvidenceLevel.HYPOTHESIS,
                source="Foldseek-KNN",
                derivation={"via_genes": ["Bbb"], "confidence": 0.7},
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
                q_value=0.01,
                direction=DifferentialDirection.UP,
                is_differential=True,
            )
        ]
    )
    run_disease_enrichment(EXP, repository=repo, min_overlap=1)
    verify_experiment_hypotheses(
        EXP,
        repository=repo,
        source=InMemoryLiteratureSource(
            by_disease={"D002": [EvidenceRecord(EvidenceStance.REFUTE, "t", "PMID:9", "lit")]}
        ),
    )  # D002 → REFUTED；D003 无证据 → 未决
    freeze_experiment(EXP, snapshot_version="1.0", pipeline_version="pipe-1", repository=repo)
    return repo


def test_report_has_layered_sections_and_traceable_statements() -> None:
    repo = _frozen_repo()
    report = generate_experiment_report(EXP, "1.0", repository=repo)

    assert report.snapshot_version == "1.0"
    assert "# 实验报告 — exp_rep" in report.markdown
    assert len(report.sections) == 8  # 设计/差异/富集/结论/假说/伪理/未决 + 附录

    md = report.markdown
    # 结论（公共事实）可追溯：疾病 + annotation_id + 来源
    assert "Brain Ischemia" in md and "ann_conc" in md and "CTD (v2026_03)" in md
    # 实验观察：差异蛋白进正文
    assert "prot1" in md and "log2FC" in md
    # 反驳 → 伪理，未决 → 未决项
    assert "ann_hypA" in md  # REFUTED
    assert "ann_hypB" in md  # 未决
    assert "PMID:9" in md    # 反证可追溯
    # 附录：蛋白基础注释
    assert "ann_base" in md and "function:kinase" in md


def test_report_is_deterministic() -> None:
    repo = _frozen_repo()
    first = generate_experiment_report(EXP, "1.0", repository=repo)
    second = generate_experiment_report(EXP, "1.0", repository=repo)
    assert first.checksum == second.checksum
    assert first.markdown == second.markdown


def test_report_reads_frozen_snapshot_not_live_state() -> None:
    repo = _frozen_repo()
    before = generate_experiment_report(EXP, "1.0", repository=repo)
    # 冻结后再改活库，不应影响已冻结版本的报告
    repo.add_annotations(
        [
            MetaAnnotation(
                annotation_id="ann_late",
                experiment_id=EXP,
                target="Casp3",
                target_type=AnnotationTargetType.GENE,
                attribute="disease:D999",
                value={"disease_id": "D999", "disease_name": "Late"},
                evidence_level=EvidenceLevel.CONCLUSION,
                source="CTD",
            )
        ]
    )
    after = generate_experiment_report(EXP, "1.0", repository=repo)
    assert after.checksum == before.checksum
    assert "ann_late" not in after.markdown


def test_report_rejects_tampered_snapshot() -> None:
    repo = InMemoryExperimentRepository()
    repo.save_snapshot(
        ExperimentSnapshot(
            experiment_id="e",
            snapshot_version="1.0",
            pipeline_version="p",
            checksum="wrong-checksum",
            manifest={"context": {}, "annotations": []},
        )
    )
    with pytest.raises(ValueError, match="integrity"):
        generate_experiment_report("e", "1.0", repository=repo)


def test_unknown_snapshot_version_raises() -> None:
    repo = _frozen_repo()
    with pytest.raises(ValueError):
        generate_experiment_report(EXP, "9.9", repository=repo)
