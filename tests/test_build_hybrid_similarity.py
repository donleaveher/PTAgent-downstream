"""阶段5 混合检索 graph 编排测试（假 store：语料→检索→写边，不连 Neo4j）。"""
from __future__ import annotations

from typing import Any

import application.graph.embed_knn as mod
from application.graph.embed_knn import build_hybrid_similarity


class _FakeGraph:
    def __init__(self, corpus: list[dict[str, Any]]) -> None:
        self._corpus = corpus
        self.pairs: list[dict[str, Any]] | None = None

    def peptide_corpus(self) -> list[dict[str, Any]]:
        return self._corpus

    def write_similarity(self, pairs: list[dict[str, Any]], batch: int = 1000) -> int:
        self.pairs = pairs
        return len(pairs)


def test_wires_corpus_to_similarity_edges(monkeypatch) -> None:
    corpus = [
        {"peptidoform": "PEPTIDEK", "seq": "PEPTIDEK", "attrs": ["GO:1"]},
        {"peptidoform": "PEPTIDER", "seq": "PEPTIDER", "attrs": ["GO:1"]},
        {"peptidoform": "ZZZZZZZZ", "seq": "ZZZZZZZZ", "attrs": []},
    ]
    fake = _FakeGraph(corpus)
    monkeypatch.setattr(mod, "get_graph_store", lambda: fake)

    res = build_hybrid_similarity(k=2)

    assert res["queries"] == 3
    assert res["edges"] == len(fake.pairs)
    pk = [p["dst"] for p in fake.pairs if p["src"] == "PEPTIDEK"]
    assert "PEPTIDER" in pk             # 共享 k-mer + 属性
    assert "PEPTIDEK" not in pk         # 不连自己
    assert "ZZZZZZZZ" not in pk         # 无共享
    assert all({"src", "dst", "score"} <= set(p) for p in fake.pairs)


def test_dense_channel_injected_into_orchestrator(monkeypatch) -> None:
    corpus = [
        {"peptidoform": "AAAAAAAA", "seq": "AAAAAAAA", "attrs": []},
        {"peptidoform": "BBBBBBBB", "seq": "BBBBBBBB", "attrs": []},
    ]
    fake = _FakeGraph(corpus)
    monkeypatch.setattr(mod, "get_graph_store", lambda: fake)

    res = build_hybrid_similarity(k=1, dense_neighbors={"AAAAAAAA": ["BBBBBBBB"]})

    pa = [p["dst"] for p in fake.pairs if p["src"] == "AAAAAAAA"]
    assert pa == ["BBBBBBBB"]           # 序列不相似，靠稠密通道连上
    assert res["queries"] == 2
