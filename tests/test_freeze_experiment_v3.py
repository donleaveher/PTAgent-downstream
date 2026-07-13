"""§9 实验冻结归档测试：FINAL 快照 + manifest/checksum、前置检查、只读、版本化、篡改检测。"""
from __future__ import annotations

import pytest

from application.experiment.freeze import (
    FreezePreconditionError,
    freeze_experiment,
    verify_snapshot_integrity,
)
from application.knowledge.deep_search import verify_experiment_hypotheses
from pkg.deep_search import EvidenceRecord, EvidenceStance, InMemoryLiteratureSource
from pkg.experiment import (
    AnnotationTargetType,
    DifferentialDirection,
    DifferentialResult,
    EvidenceLevel,
    ExperimentBundle,
    ExperimentContext,
    ExperimentGroup,
    ExperimentStatus,
    GroupRole,
    InMemoryExperimentRepository,
    MetaAnnotation,
    ProteinRecord,
    RequestVersionConflict,
)

EXP = "exp_freeze"


def _ready_repo(run_deep_search: bool = True) -> InMemoryExperimentRepository:
    repo = InMemoryExperimentRepository()
    repo.save_bundle(
        ExperimentBundle(
            context=ExperimentContext(experiment_id=EXP, raw_text="ischemia", organism="rat"),
            groups=[
                ExperimentGroup(group_id="case", label="Case", role=GroupRole.CASE),
                ExperimentGroup(group_id="ctrl", label="Control", role=GroupRole.CONTROL),
            ],
            proteins=[
                ProteinRecord(protein_id="prot1", accession="P1", gene="Stat3", taxon_id=10116)
            ],
            peptides=[],
        )
    )
    repo.add_annotations(
        [
            MetaAnnotation(
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
            MetaAnnotation(
                annotation_id="ann_hyp",
                experiment_id=EXP,
                target="prot1",
                target_type=AnnotationTargetType.PROTEIN,
                attribute="disease:D002",
                value={"disease_id": "D002", "disease_name": "Inflammation"},
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
            )
        ]
    )
    if run_deep_search:
        source = InMemoryLiteratureSource(
            by_disease={"D002": [EvidenceRecord(EvidenceStance.SUPPORT, "t", "PMID:1", "lit")]}
        )
        verify_experiment_hypotheses(EXP, repository=repo, source=source)
    return repo


def test_freeze_creates_final_snapshot_with_manifest_and_checksum() -> None:
    repo = _ready_repo()
    snap = freeze_experiment(
        EXP,
        snapshot_version="1.0",
        pipeline_version="pipe-1",
        repository=repo,
        model_version="m1",
        query_and_params={"alpha": 0.05},
    )

    assert snap.status is ExperimentStatus.FINAL
    assert snap.snapshot_version == "1.0"
    assert snap.checksum
    assert snap.general_kg_version["CTD"] == "2026_03"
    assert snap.manifest["counts"]["annotations"] == 2
    # deep-search 把 D002 假说升为结论 → 两条都是结论
    assert snap.manifest["evidence_levels"]["CONCLUSION"] == 2
    assert snap.manifest["evidence_levels"]["HYPOTHESIS"] == 0
    assert snap.manifest["graph"]["nodes"] >= 1
    assert snap.manifest["graph"]["schema_version"] == "2"
    assert len(snap.manifest["graph"]["checksum"]) == 64
    assert snap.manifest["graph"]["nodes"] == len(
        snap.manifest["graph"]["node_records"]
    )
    assert snap.manifest["graph"]["edges"] == len(
        snap.manifest["graph"]["edge_records"]
    )
    gnn = snap.manifest["graph"]["gnn_export"]
    assert len(gnn["node_table"]) == snap.manifest["graph"]["nodes"]
    assert len(gnn["edge_index"]) == snap.manifest["graph"]["edges"]
    assert len(gnn["checksum"]) == 64
    assert snap.manifest["counts"]["annotation_history"] == 1
    assert snap.manifest["counts"]["deep_search_evidence"] == 1
    assert snap.manifest["deep_search"]["evidence_by_stance"] == {
        "support": 1,
        "refute": 0,
        "neutral": 0,
    }
    assert snap.manifest["deep_search_evidence"][0]["reference"] == "PMID:1"
    assert verify_snapshot_integrity(snap)
    assert repo.get_snapshot(snap.snapshot_id) == snap  # 读回一致


def test_old_version_unchanged_after_new_evidence() -> None:
    repo = _ready_repo()
    snap1 = freeze_experiment(EXP, snapshot_version="1.0", pipeline_version="pipe-1", repository=repo)

    # 新证据：再补一条结论 → 冻新版本，旧版本内容必须保持不变
    repo.add_annotations(
        [
            MetaAnnotation(
                annotation_id="ann_new",
                experiment_id=EXP,
                target="Stat3",
                target_type=AnnotationTargetType.GENE,
                attribute="disease:D003",
                value={"disease_id": "D003", "disease_name": "New"},
                evidence_level=EvidenceLevel.CONCLUSION,
                source="CTD",
                provenance={"db_version": "2026_04"},
            )
        ]
    )
    snap2 = freeze_experiment(EXP, snapshot_version="1.1", pipeline_version="pipe-1", repository=repo)

    snap1_read = repo.get_snapshot(snap1.snapshot_id)
    assert snap1_read is not None
    assert snap1_read.manifest["counts"]["annotations"] == 2  # 旧版本不变
    assert snap2.manifest["counts"]["annotations"] == 3       # 新版本含新证据
    assert verify_snapshot_integrity(snap1_read)
    assert {s.snapshot_version for s in repo.list_snapshots(EXP)} == {"1.0", "1.1"}


def test_new_version_supersedes_prior() -> None:
    repo = _ready_repo()
    snap1 = freeze_experiment(EXP, snapshot_version="1.0", pipeline_version="p", repository=repo)
    assert repo.get_snapshot(snap1.snapshot_id).status is ExperimentStatus.FINAL  # 唯一 FINAL

    snap2 = freeze_experiment(EXP, snapshot_version="1.1", pipeline_version="p", repository=repo)
    by_id = {s.snapshot_id: s for s in repo.list_snapshots(EXP)}
    assert by_id[snap1.snapshot_id].status is ExperimentStatus.SUPERSEDED  # 旧版被标记
    assert by_id[snap2.snapshot_id].status is ExperimentStatus.FINAL       # 新版当前
    # 不删：旧版仍在、仍可读、仍自洽
    assert {s.snapshot_version for s in repo.list_snapshots(EXP)} == {"1.0", "1.1"}
    assert verify_snapshot_integrity(by_id[snap1.snapshot_id])


def test_supersede_prior_can_be_disabled() -> None:
    repo = _ready_repo()
    snap1 = freeze_experiment(EXP, snapshot_version="1.0", pipeline_version="p", repository=repo)
    freeze_experiment(
        EXP, snapshot_version="1.1", pipeline_version="p", repository=repo, supersede_prior=False
    )
    by_id = {s.snapshot_id: s for s in repo.list_snapshots(EXP)}
    assert by_id[snap1.snapshot_id].status is ExperimentStatus.FINAL  # 关掉 → 旧版仍 FINAL


def test_tamper_is_detected() -> None:
    repo = _ready_repo()
    snap = freeze_experiment(EXP, snapshot_version="1.0", pipeline_version="pipe-1", repository=repo)
    snap.manifest["counts"]["annotations"] = 999  # 篡改
    assert verify_snapshot_integrity(snap) is False


def test_precondition_blocks_unprocessed_hypotheses() -> None:
    repo = _ready_repo(run_deep_search=False)  # D002 假说未经 deep-search
    with pytest.raises(FreezePreconditionError):
        freeze_experiment(EXP, snapshot_version="1.0", pipeline_version="p", repository=repo)

    snap = freeze_experiment(
        EXP,
        snapshot_version="1.0",
        pipeline_version="p",
        repository=repo,
        allow_unresolved_hypotheses=True,
    )
    assert snap.manifest["evidence_levels"]["HYPOTHESIS"] == 1


def test_freeze_prevents_overwriting_same_version() -> None:
    repo = _ready_repo()
    freeze_experiment(EXP, snapshot_version="1.0", pipeline_version="p", repository=repo)
    with pytest.raises(RequestVersionConflict):
        freeze_experiment(EXP, snapshot_version="1.0", pipeline_version="p", repository=repo)


def test_unknown_experiment_raises() -> None:
    with pytest.raises(ValueError):
        freeze_experiment(
            "nope",
            snapshot_version="1.0",
            pipeline_version="p",
            repository=InMemoryExperimentRepository(),
        )
