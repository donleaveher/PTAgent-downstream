"""阶段3.5 注释富集编排测试（假图 store + 假注释源，不连 Neo4j/不读 TSV）。"""
from __future__ import annotations

from typing import Any

import application.graph.enrich_annot as mod
from application.graph.enrich_annot import enrich_proteins


class _FakeGraph:
    def __init__(self, todo: list[dict[str, Any]]) -> None:
        self._todo = todo
        self.written: list[dict[str, Any]] | None = None

    def list_unannotated_proteins(self) -> list[dict[str, Any]]:
        return self._todo

    def write_annotations(self, rows: list[dict[str, Any]], batch: int = 500) -> int:
        self.written = rows
        return len(rows)


class _FakeSource:
    name = "FakeSrc"
    version = "2026_01"

    def fetch(self, accs: list[str]) -> dict[str, dict[str, list[str]]]:
        data = {
            "A1": {"go": ["GO:1"], "ec": ["1.1.1.1"], "interpro": ["IPR1"]},
            "A2": {"go": [], "ec": [], "interpro": ["IPR2"]},
        }
        return {a: data[a] for a in accs if a in data}


def test_enrich_writes_found_skips_unknown(monkeypatch) -> None:
    fake = _FakeGraph([{"accession": "A1"}, {"accession": "A2"}, {"accession": "A3"}])
    monkeypatch.setattr(mod, "get_graph_store", lambda: fake)

    res = enrich_proteins(source=_FakeSource())

    assert res == {"unannotated": 3, "enriched": 2}          # A3 源里没有 → 不写
    by_acc = {r["accession"]: r for r in fake.written}
    assert set(by_acc) == {"A1", "A2"}
    assert by_acc["A1"]["go"] == ["GO:1"]
    assert by_acc["A1"]["ec"] == ["1.1.1.1"]
    assert by_acc["A1"]["interpro"] == ["IPR1"]
    assert by_acc["A2"]["interpro"] == ["IPR2"]
    # provenance 带上源名/版本
    assert all(r["source"] == "FakeSrc" and r["version"] == "2026_01" for r in fake.written)


def test_enrich_dedupes_accessions(monkeypatch) -> None:
    fake = _FakeGraph([{"accession": "A1"}, {"accession": "A1"}])   # 重复
    monkeypatch.setattr(mod, "get_graph_store", lambda: fake)

    res = enrich_proteins(source=_FakeSource())

    assert res == {"unannotated": 1, "enriched": 1}          # 去重后只 1 个
    assert [r["accession"] for r in fake.written] == ["A1"]


def test_enrich_empty(monkeypatch) -> None:
    fake = _FakeGraph([])
    monkeypatch.setattr(mod, "get_graph_store", lambda: fake)

    res = enrich_proteins(source=_FakeSource())

    assert res == {"unannotated": 0, "enriched": 0}
    assert fake.written is None                              # 空：不回写
