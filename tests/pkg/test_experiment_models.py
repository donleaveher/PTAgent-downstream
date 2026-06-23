"""新版实验输入与证据域模型。"""

from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from pkg.experiment import (
    AnnotationTargetType,
    DifferentialDirection,
    DifferentialResult,
    EvidenceLevel,
    ExperimentBundle,
    ExperimentSnapshot,
    ExperimentStatus,
    InMemoryExperimentRepository,
    MetaAnnotation,
    ProteinQuantification,
    RequestVersionConflict,
    ingest_experiment_payload,
)


def valid_payload() -> dict:
    return {
        "context": {
            "experiment_id": "exp_1",
            "session_id": "sess_1",
            "title": "JAK2 CIRI",
            "raw_text": "大鼠 tMCAO，shJAK2 与对照组 DIA 比较",
            "disease": ["CIRI"],
            "pathway": ["JAK2/STAT3"],
            "organism": "Rattus norvegicus",
            "taxon_id": 10116,
            "assay": "DIA",
        },
        "groups": [
            {"group_id": "g_case", "label": "shJAK2", "role": "case"},
            {"group_id": "g_ctrl", "label": "shNC", "role": "control"},
        ],
        "proteins": [
            {
                "protein_id": "prot_1",
                "accession": "P12345",
                "gene": "Jak2",
                "organism": "Rattus norvegicus",
                "taxon_id": 10116,
                "peptide_ids": ["pep_1", "pep_2"],
            }
        ],
        "peptides": [
            {
                "peptide_id": "pep_1",
                "peptidoform": "PEPTIDEK",
                "stripped_sequence": "PEPTIDEK",
                "protein_id": "prot_1",
                "spectrum_ids": ["spec_1"],
                "confidence": 0.98,
                "group_label": "shJAK2",
                "abundance": 1200.0,
            },
            {
                "peptide_id": "pep_2",
                "peptidoform": "PEPTIDER",
                "stripped_sequence": "PEPTIDER",
                "protein_id": "prot_1",
                "spectrum_ids": ["spec_2"],
                "confidence": 0.95,
                "group_label": "shNC",
                "abundance": 800.0,
            },
        ],
    }


def test_bundle_validates_cross_references() -> None:
    bundle = ExperimentBundle.model_validate(valid_payload())
    assert bundle.context.experiment_id == "exp_1"
    assert bundle.groups[0].role.value == "case"
    assert bundle.proteins[0].peptide_ids == ["pep_1", "pep_2"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda p: p["peptides"][0].update(group_label="missing"), "unknown group label"),
        (lambda p: p["peptides"][0].update(protein_id="missing"), "unknown protein"),
        (lambda p: p["proteins"][0].update(peptide_ids=["missing"]), "unknown peptide"),
        (lambda p: p["groups"].append(copy.deepcopy(p["groups"][0])), "duplicate group_id"),
    ],
)
def test_bundle_rejects_invalid_references(mutate, message: str) -> None:
    payload = valid_payload()
    mutate(payload)
    with pytest.raises(ValidationError, match=message):
        ExperimentBundle.model_validate(payload)


def test_ingest_validates_before_writing() -> None:
    repo = InMemoryExperimentRepository()
    bundle = ingest_experiment_payload(valid_payload(), repo)
    assert repo.get_context("exp_1") == bundle.context
    assert repo.get_bundle("exp_1") == bundle
    assert [g.group_id for g in repo.list_groups("exp_1")] == ["g_case", "g_ctrl"]
    assert [p.protein_id for p in repo.list_proteins("exp_1")] == ["prot_1"]
    assert len(repo.list_peptides("exp_1")) == 2


def test_annotations_are_experiment_scoped() -> None:
    repo = InMemoryExperimentRepository()
    ingest_experiment_payload(valid_payload(), repo)
    annotation = MetaAnnotation(
        annotation_id="ann_1",
        experiment_id="exp_1",
        target="prot_1",
        target_type=AnnotationTargetType.PROTEIN,
        attribute="domain:SH2",
        value="SH2",
        evidence_level=EvidenceLevel.CONCLUSION,
        source="UniProt-MCP",
    )
    assert repo.add_annotations([annotation]) == 1
    assert repo.list_annotations("exp_1") == [annotation]
    assert repo.list_annotations("exp_other") == []


def test_snapshot_cannot_be_working() -> None:
    with pytest.raises(ValidationError, match="cannot have WORKING status"):
        ExperimentSnapshot(
            experiment_id="exp_1",
            snapshot_version="1.0",
            status=ExperimentStatus.WORKING,
            pipeline_version="test",
            checksum="abc",
        )


def test_inmemory_snapshot_is_append_only_and_version_unique() -> None:
    repo = InMemoryExperimentRepository()
    ingest_experiment_payload(valid_payload(), repo)
    snapshot = ExperimentSnapshot(
        snapshot_id="snap_1",
        experiment_id="exp_1",
        snapshot_version="1.0",
        pipeline_version="pipe-v1",
        checksum="sum-1",
    )
    repo.save_snapshot(snapshot)
    assert repo.get_snapshot("snap_1") == snapshot
    assert repo.list_snapshots("exp_1") == [snapshot]
    with pytest.raises(RequestVersionConflict, match="version already exists"):
        repo.save_snapshot(
            ExperimentSnapshot(
                snapshot_id="snap_2",
                experiment_id="exp_1",
                snapshot_version="1.0",
                pipeline_version="pipe-v1",
                checksum="sum-2",
            )
        )


def test_inmemory_quantification_and_differential_round_trip() -> None:
    repo = InMemoryExperimentRepository()
    ingest_experiment_payload(valid_payload(), repo)
    quant = ProteinQuantification(
        quantification_id="q1",
        experiment_id="exp_1",
        protein_id="prot_1",
        group_id="g_case",
        sample_id="s1",
        abundance=12.0,
    )
    assert repo.add_quantifications([quant]) == 1
    assert repo.list_quantifications("exp_1") == [quant]
    diff = DifferentialResult(
        differential_id="d1",
        experiment_id="exp_1",
        protein_id="prot_1",
        case_group_id="g_case",
        control_group_id="g_ctrl",
        log2fc=1.5,
        direction=DifferentialDirection.UP,
        is_differential=True,
    )
    assert repo.add_differentials([diff]) == 1
    assert repo.list_differentials("exp_1") == [diff]
