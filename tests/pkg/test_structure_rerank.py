"""结构近邻 RRF 融合重排单测（复用 pkg.retrieval 的 rrf）。"""
from __future__ import annotations

from pkg.structure import StructuralNeighbor, rerank_neighbors


def _n(target: str, score: float, coverage: float) -> StructuralNeighbor:
    return StructuralNeighbor(
        query_accession="Q", target_accession=target, score=score, coverage=coverage
    )


def test_empty_returns_empty() -> None:
    assert rerank_neighbors([]) == []


def test_single_neighbor_passthrough() -> None:
    out = rerank_neighbors([_n("A", 0.9, 0.5)])
    assert len(out) == 1
    assert out[0][0].target_accession == "A" and out[0][1] > 0


def test_coverage_can_outrank_higher_score() -> None:
    # 纯 score 序为 A>B>C；但 B 覆盖度最高，RRF 融合后 B 升到首位
    neighbors = [_n("A", 0.9, 0.10), _n("B", 0.8, 0.99), _n("C", 0.7, 0.98)]
    ranked = [n.target_accession for n, _ in rerank_neighbors(neighbors)]
    assert ranked[0] == "B"
    assert ranked != ["A", "B", "C"]  # 不等于纯 score 序


def test_descending_fused_scores() -> None:
    out = rerank_neighbors([_n("A", 0.9, 0.10), _n("B", 0.8, 0.99), _n("C", 0.7, 0.98)])
    scores = [fs for _, fs in out]
    assert scores == sorted(scores, reverse=True)


def test_extra_channel_raises_fused_score() -> None:
    # 三者基线打平；注入偏向 C 的额外召回路 → C 的融合分上升
    neighbors = [_n("A", 0.8, 0.8), _n("B", 0.8, 0.8), _n("C", 0.8, 0.8)]
    base = {n.target_accession: fs for n, fs in rerank_neighbors(neighbors)}
    boosted = {
        n.target_accession: fs
        for n, fs in rerank_neighbors(neighbors, extra_channels=[["C", "B", "A"]])
    }
    assert boosted["C"] > base["C"]
