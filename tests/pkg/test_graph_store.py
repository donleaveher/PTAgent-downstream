"""图谱 store 的 Python 侧契约测试（不连 Neo4j）。

做法：用假 store 拦截 ``run``，验"方法把哪条 Cypher、什么参数、怎么分批"发出去 +
几条新 Cypher 的结构。注：Cypher 的**语义**对错需真 Neo4j，属集成测试，此处不覆盖。
"""
from __future__ import annotations

from typing import Any

from pkg.graph import cypher
from pkg.graph.store import GraphStore


class _RecordingStore(GraphStore):
    """不建 driver、把 run 换成记录器；只测方法发出去的 Cypher/参数/分批。"""

    def __init__(self) -> None:                       # 故意不调 super().__init__（不连库）
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.ret: list[dict[str, Any]] = []

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        self.calls.append((query, params))
        return self.ret


def test_write_lookup_batches_and_uses_merge_pep_lookup() -> None:
    store = _RecordingStore()
    rows = [
        {"peptidoform": f"P{i}", "db_hit": i % 2 == 0,
         "db_name": "UniProt", "db_version": "2026_01"}
        for i in range(2500)
    ]
    n = store.write_lookup(rows, batch=1000)
    assert n == 2500
    assert len(store.calls) == 3                                   # 2500/1000 → 3 批
    assert all(q == cypher.MERGE_PEP_LOOKUP for q, _ in store.calls)
    assert sum(len(p["rows"]) for _, p in store.calls) == 2500     # 参数键是 rows、不丢行


def test_write_annotations_uses_merge_prot_annot() -> None:
    store = _RecordingStore()
    rows = [{"accession": "P12345", "go": ["GO:1"], "ec": [],
             "interpro": ["IPR1"], "version": "2026_01"}]
    n = store.write_annotations(rows)
    assert n == 1
    assert store.calls and store.calls[0][0] == cypher.MERGE_PROT_ANNOT
    assert store.calls[0][1]["rows"] == rows


def test_list_queries_route_to_right_cypher() -> None:
    store = _RecordingStore()
    store.ret = [{"peptidoform": "P1", "seq": "ABC"}]
    assert store.list_novel_peptides() == store.ret
    assert store.calls[-1][0] == cypher.Q_NOVEL_PEPTIDES

    store.ret = [{"accession": "P12345"}]
    assert store.list_unannotated_proteins() == store.ret
    assert store.calls[-1][0] == cypher.Q_UNANNOTATED


def test_empty_rows_make_no_calls() -> None:
    store = _RecordingStore()
    assert store.write_lookup([]) == 0
    assert store.write_annotations([]) == 0
    assert store.calls == []


def test_cypher_statements_have_expected_shape() -> None:
    # novelty：is_novel 由 NOT db_hit 派生；只 MATCH 不 MERGE（不凭空造节点）
    assert "MATCH (p:Peptide" in cypher.MERGE_PEP_LOOKUP
    assert "is_novel" in cypher.MERGE_PEP_LOOKUP
    assert "NOT r.db_hit" in cypher.MERGE_PEP_LOOKUP
    assert "MERGE" not in cypher.MERGE_PEP_LOOKUP

    # 富集：只 MATCH 已有 Protein，写 go/ec/interpro + 版本
    assert "MATCH (pr:Protein" in cypher.MERGE_PROT_ANNOT
    for prop in ("pr.go", "pr.ec", "pr.interpro", "annot_version"):
        assert prop in cypher.MERGE_PROT_ANNOT
    assert "MERGE" not in cypher.MERGE_PROT_ANNOT

    # 两个新索引进了 schema
    idx = " ".join(cypher.INDEXES)
    assert "pep_novel" in idx and "prot_annot" in idx


def test_new_types_exported() -> None:
    from pkg.graph import HypothesisRow, PepLookupRow, ProtAnnotRow  # noqa: F401
