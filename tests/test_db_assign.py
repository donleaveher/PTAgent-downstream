"""阶段3 查库归属编排测试（假图 store + 假蛋白库，不连 Neo4j/不读 FASTA）。"""
from __future__ import annotations

from typing import Any

import application.graph.db_assign as mod
from application.graph.db_assign import assign_proteins


class _FakeGraph:
    """记录 assign 回写了什么；list_unsearched_peptides 返回喂进来的 todo。"""

    def __init__(self, todo: list[dict[str, Any]]) -> None:
        self._todo = todo
        self.pep_prot: list[dict[str, Any]] | None = None
        self.lookup: list[dict[str, Any]] | None = None

    def list_unsearched_peptides(self) -> list[dict[str, Any]]:
        return self._todo

    def merge_pep_prot(self, rows: list[dict[str, Any]], batch: int = 1000) -> int:
        self.pep_prot = rows
        return len(rows)

    def write_lookup(self, rows: list[dict[str, Any]], batch: int = 1000) -> int:
        self.lookup = rows
        return len(rows)


class _FakeDB:
    name = "FakeDB"
    version = "v1"

    def lookup(self, seq: str) -> list[dict[str, str]]:
        return [{"accession": "P1", "description": "alpha"}] if seq == "HIT" else []


def test_assign_proteins_splits_hit_and_novel(monkeypatch) -> None:
    fake = _FakeGraph([
        {"peptidoform": "HIT", "seq": "HIT"},
        {"peptidoform": "NOVELX", "seq": "NOVELX"},
    ])
    monkeypatch.setattr(mod, "get_graph_store", lambda: fake)

    res = assign_proteins(db=_FakeDB())

    assert res == {"searched": 2, "hits": 1, "novel": 1}
    # 命中边：只对命中的肽建
    assert fake.pep_prot == [
        {"peptidoform": "HIT", "accession": "P1", "description": "alpha"}
    ]
    # novelty：两条都写，命中 True / 未命中 False，且带库名版本
    by_pep = {r["peptidoform"]: r for r in fake.lookup}
    assert by_pep["HIT"]["db_hit"] is True
    assert by_pep["NOVELX"]["db_hit"] is False
    assert all(r["db_name"] == "FakeDB" and r["db_version"] == "v1" for r in fake.lookup)


def test_assign_proteins_empty(monkeypatch) -> None:
    fake = _FakeGraph([])
    monkeypatch.setattr(mod, "get_graph_store", lambda: fake)

    res = assign_proteins(db=_FakeDB())

    assert res == {"searched": 0, "hits": 0, "novel": 0}
    assert fake.pep_prot is None and fake.lookup is None     # 空：不回写
