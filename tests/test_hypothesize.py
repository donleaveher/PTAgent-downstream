"""阶段6 假说编排测试（假 store：邻居母蛋白注释→共识→HypothesisRow，不连 Neo4j）。"""
from __future__ import annotations

from typing import Any

import application.graph.hypothesize as mod
from application.graph.hypothesize import hypothesize_novel, hypothesize_peptide


class _FakeGraph:
    def __init__(self, nb_by_pep: dict[str, list[dict[str, Any]]],
                 novel: list[dict[str, Any]]) -> None:
        self._nb = nb_by_pep
        self._novel = novel

    def neighbor_annotations(self, peptidoform: str) -> list[dict[str, Any]]:
        return self._nb.get(peptidoform, [])

    def list_novel_peptides(self) -> list[dict[str, Any]]:
        return self._novel


def test_hypothesize_peptide_keeps_protein_provenance(monkeypatch) -> None:
    # Q_NEIGHBOR_ANNOTS 返回 proteins 是 map 列表；k2 是共享肽(两个蛋白)
    nb = {
        "NOVEL1": [
            {"id": "k1", "score": 0.9, "proteins": [
                {"accession": "P1", "go": ["GO:1"], "ec": [], "interpro": []}]},
            {"id": "k2", "score": 0.8, "proteins": [
                {"accession": "P1", "go": ["GO:1"], "ec": [], "interpro": []},
                {"accession": "P2", "go": ["GO:1"], "ec": [], "interpro": []}]},
        ]
    }
    monkeypatch.setattr(mod, "get_graph_store", lambda: _FakeGraph(nb, []))

    rows = hypothesize_peptide("NOVEL1")
    top = rows[0]
    assert top["peptidoform"] == "NOVEL1"
    assert top["attr_type"] == "go" and top["predicted"] == "GO:1"
    assert set(top) == {"peptidoform", "attr_type", "predicted", "support", "confidence"}
    via = {s["neighbor"]: s["via"] for s in top["support"]}
    assert via["k1"] == ["P1"]
    assert sorted(via["k2"]) == ["P1", "P2"]                    # 共享肽出处保住


def test_hypothesize_novel_only_keeps_those_with_predictions(monkeypatch) -> None:
    nb = {
        "NOVEL1": [{"id": "k1", "score": 0.9, "proteins": [
            {"accession": "P1", "go": ["GO:1"], "ec": [], "interpro": []}]}],
        # NOVEL2 无邻居 → 无假说
    }
    novel = [{"peptidoform": "NOVEL1", "seq": "AAA"}, {"peptidoform": "NOVEL2", "seq": "BBB"}]
    monkeypatch.setattr(mod, "get_graph_store", lambda: _FakeGraph(nb, novel))

    res = hypothesize_novel()
    assert res["novel"] == 2
    assert res["with_hypotheses"] == 1
    assert set(res["hypotheses"]) == {"NOVEL1"}
