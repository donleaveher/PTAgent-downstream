"""L4 deep-search 纯状态机 + 检索源契约测试。"""
from __future__ import annotations

import pytest

from pkg.deep_search import (
    DeepSearchTask,
    DeepSearchVerdict,
    EvidenceRecord,
    EvidenceStance,
    InMemoryLiteratureSource,
    LiteratureSearchSource,
    decide_verdict,
    get_literature_search_source,
)
from pkg.experiment import EvidenceLevel

H = EvidenceLevel.HYPOTHESIS


def _ev(stance: EvidenceStance, ref: str) -> EvidenceRecord:
    return EvidenceRecord(stance=stance, title="t", reference=ref, source="src")


def test_support_only_promotes_to_conclusion() -> None:
    out = decide_verdict(H, [_ev(EvidenceStance.SUPPORT, "PMID:2"), _ev(EvidenceStance.SUPPORT, "PMID:1")])
    assert out.verdict is DeepSearchVerdict.SUPPORTED
    assert out.to_level is EvidenceLevel.CONCLUSION
    assert out.changed is True
    assert out.support_refs == ("PMID:1", "PMID:2")  # 排序、确定性
    assert out.refute_refs == ()


def test_refute_only_marks_refuted() -> None:
    out = decide_verdict(H, [_ev(EvidenceStance.REFUTE, "PMID:9")])
    assert out.verdict is DeepSearchVerdict.REFUTED
    assert out.to_level is EvidenceLevel.REFUTED
    assert out.changed is True


def test_conflicting_stays_hypothesis() -> None:
    out = decide_verdict(
        H, [_ev(EvidenceStance.SUPPORT, "PMID:1"), _ev(EvidenceStance.REFUTE, "PMID:2")]
    )
    assert out.verdict is DeepSearchVerdict.CONFLICTING
    assert out.to_level is EvidenceLevel.HYPOTHESIS
    assert out.changed is False


def test_no_or_neutral_evidence_is_insufficient() -> None:
    assert decide_verdict(H, []).verdict is DeepSearchVerdict.INSUFFICIENT
    out = decide_verdict(H, [_ev(EvidenceStance.NEUTRAL, "PMID:5")])
    assert out.verdict is DeepSearchVerdict.INSUFFICIENT
    assert out.to_level is EvidenceLevel.HYPOTHESIS
    assert out.changed is False


def test_inmemory_source_returns_by_disease_and_satisfies_port() -> None:
    src = InMemoryLiteratureSource(
        by_disease={"MESH:D1": [_ev(EvidenceStance.SUPPORT, "PMID:1")]}
    )
    assert isinstance(src, LiteratureSearchSource)
    task = DeepSearchTask(
        annotation_id="a",
        experiment_id="e",
        protein_id="p",
        gene="G",
        disease_id="MESH:D1",
        disease_name="D1",
    )
    assert [e.reference for e in src.search(task)] == ["PMID:1"]
    miss = DeepSearchTask(
        annotation_id="a",
        experiment_id="e",
        protein_id="p",
        gene="G",
        disease_id="MESH:DX",
        disease_name="DX",
    )
    assert src.search(miss) == []


def test_production_source_factory_refuses_mock() -> None:
    with pytest.raises(NotImplementedError):
        get_literature_search_source()
