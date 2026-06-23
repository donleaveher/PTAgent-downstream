"""L4 deep-search 服务测试：认知态跃迁、幂等、历史可回放、人工覆盖、隔离。"""
from __future__ import annotations

import pytest

from application.knowledge.deep_search import (
    override_hypothesis_verdict,
    verify_experiment_hypotheses,
)
from pkg.deep_search import EvidenceRecord, EvidenceStance, InMemoryLiteratureSource
from pkg.experiment import (
    AnnotationTargetType,
    EvidenceLevel,
    ExperimentBundle,
    ExperimentContext,
    ExperimentGroup,
    GroupRole,
    InMemoryExperimentRepository,
    MetaAnnotation,
    ProteinRecord,
)

EXP = "exp_ds"


def _hyp(annotation_id: str, protein_id: str, disease_id: str) -> MetaAnnotation:
    return MetaAnnotation(
        annotation_id=annotation_id,
        experiment_id=EXP,
        target=protein_id,
        target_type=AnnotationTargetType.PROTEIN,
        attribute=f"disease:{disease_id}",
        value={"disease_id": disease_id, "disease_name": disease_id},
        evidence_level=EvidenceLevel.HYPOTHESIS,
        source="Foldseek-KNN",
    )


def _ev(stance: EvidenceStance, ref: str) -> EvidenceRecord:
    return EvidenceRecord(stance=stance, title="t", reference=ref, source="lit")


def _seed() -> tuple[InMemoryExperimentRepository, InMemoryLiteratureSource]:
    repo = InMemoryExperimentRepository()
    repo.save_bundle(
        ExperimentBundle(
            context=ExperimentContext(experiment_id=EXP, raw_text="ischemia background"),
            groups=[ExperimentGroup(group_id="case", label="Case", role=GroupRole.CASE)],
            proteins=[
                ProteinRecord(protein_id="prot1", accession="P1", gene="Stat3"),
                ProteinRecord(protein_id="prot2", accession="P2", gene="Casp3"),
            ],
            peptides=[],
        )
    )
    repo.add_annotations(
        [
            _hyp("ann_sup", "prot1", "D_SUP"),
            _hyp("ann_ref", "prot1", "D_REF"),
            _hyp("ann_ins", "prot2", "D_INS"),
            _hyp("ann_con", "prot2", "D_CON"),
            MetaAnnotation(  # 基因结论：deep-search 不应处理
                annotation_id="ann_gene",
                experiment_id=EXP,
                target="Stat3",
                target_type=AnnotationTargetType.GENE,
                attribute="disease:D_GENE",
                value={"disease_id": "D_GENE", "disease_name": "D_GENE"},
                evidence_level=EvidenceLevel.CONCLUSION,
                source="CTD",
            ),
        ]
    )
    source = InMemoryLiteratureSource(
        by_disease={
            "D_SUP": [_ev(EvidenceStance.SUPPORT, "PMID:1")],
            "D_REF": [_ev(EvidenceStance.REFUTE, "PMID:2")],
            "D_CON": [
                _ev(EvidenceStance.SUPPORT, "PMID:3"),
                _ev(EvidenceStance.REFUTE, "PMID:4"),
            ],
            # D_INS 无证据
        }
    )
    return repo, source


def _levels(repo: InMemoryExperimentRepository) -> dict[str, EvidenceLevel]:
    return {a.annotation_id: a.evidence_level for a in repo.list_annotations(EXP)}


def test_state_machine_transitions_and_summary() -> None:
    repo, source = _seed()
    summary = verify_experiment_hypotheses(EXP, repository=repo, source=source)

    assert summary["hypotheses"] == 4  # 基因结论被排除
    assert summary["verdicts"] == {
        "supported": 1,
        "refuted": 1,
        "conflicting": 1,
        "insufficient": 1,
    }
    assert summary["annotations_updated"] == 2
    assert summary["history_appended"] == 4

    levels = _levels(repo)
    assert levels["ann_sup"] is EvidenceLevel.CONCLUSION
    assert levels["ann_ref"] is EvidenceLevel.REFUTED
    assert levels["ann_ins"] is EvidenceLevel.HYPOTHESIS
    assert levels["ann_con"] is EvidenceLevel.HYPOTHESIS
    assert levels["ann_gene"] is EvidenceLevel.CONCLUSION  # 未被触碰


def test_history_is_replayable_with_evidence() -> None:
    repo, source = _seed()
    verify_experiment_hypotheses(EXP, repository=repo, source=source)
    history = repo.list_annotation_history(EXP)
    by_ann = {h.annotation_id: h for h in history}

    assert len(history) == 4
    assert by_ann["ann_sup"].to_level is EvidenceLevel.CONCLUSION
    assert by_ann["ann_sup"].verdict == "supported"
    assert by_ann["ann_sup"].evidence_ref["support_refs"] == ["PMID:1"]
    assert by_ann["ann_ref"].to_level is EvidenceLevel.REFUTED
    assert by_ann["ann_con"].verdict == "conflicting"
    assert by_ann["ann_con"].from_level is EvidenceLevel.HYPOTHESIS
    # 未决也显式记录（保留来源/查询，可回放）
    assert by_ann["ann_ins"].verdict == "insufficient"
    assert by_ann["ann_ins"].evidence_ref["source"] == "in-memory"  # 检索工具名
    assert by_ann["ann_ins"].evidence_ref["query"]


def test_rerun_is_idempotent() -> None:
    repo, source = _seed()
    verify_experiment_hypotheses(EXP, repository=repo, source=source)
    second = verify_experiment_hypotheses(EXP, repository=repo, source=source)

    # 已跃迁的不再处理；仍为假说的两条裁决相同 → 无新历史、无新更新
    assert second["hypotheses"] == 2
    assert second["history_appended"] == 0
    assert second["annotations_updated"] == 0
    assert len(repo.list_annotation_history(EXP)) == 4


def test_new_evidence_appends_new_history() -> None:
    repo, source = _seed()
    verify_experiment_hypotheses(EXP, repository=repo, source=source)
    # 之前未决的 D_INS 现在出现支持证据 → 跃迁为结论，追加新历史
    source._by_disease["D_INS"] = [_ev(EvidenceStance.SUPPORT, "PMID:7")]
    third = verify_experiment_hypotheses(EXP, repository=repo, source=source)

    assert third["annotations_updated"] == 1
    assert _levels(repo)["ann_ins"] is EvidenceLevel.CONCLUSION
    assert len(repo.list_annotation_history(EXP)) == 5


def test_manual_override_records_operator_and_reason() -> None:
    repo, source = _seed()
    verify_experiment_hypotheses(EXP, repository=repo, source=source)
    updated = override_hypothesis_verdict(
        EXP,
        "ann_con",
        to_level=EvidenceLevel.REFUTED,
        operator="alice",
        reason="conflicting lit resolved against",
        repository=repo,
    )
    assert updated.evidence_level is EvidenceLevel.REFUTED
    assert updated.derivation["manual_override"]["operator"] == "alice"
    last = repo.list_annotation_history(EXP)[-1]
    assert last.verdict == "manual_override:alice"
    assert last.evidence_ref["reason"] == "conflicting lit resolved against"


def test_override_requires_operator_and_reason() -> None:
    repo, source = _seed()
    with pytest.raises(ValueError):
        override_hypothesis_verdict(
            EXP, "ann_sup", to_level=EvidenceLevel.REFUTED, operator="", reason="x", repository=repo
        )


def test_unknown_experiment_and_annotation_raise() -> None:
    repo, source = _seed()
    with pytest.raises(ValueError):
        verify_experiment_hypotheses("nope", repository=repo, source=source)
    with pytest.raises(ValueError):
        override_hypothesis_verdict(
            EXP, "missing", to_level=EvidenceLevel.CONCLUSION, operator="a", reason="b", repository=repo
        )
