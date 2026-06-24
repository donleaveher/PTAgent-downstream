"""结构近邻多路融合重排：把 Foldseek 单路 score 排序升级为多信号 RRF 融合。

复用通用检索骨架 :func:`pkg.retrieval.rrf`——按名次融合异构信号，量纲无关、零调参。
默认融合两路：结构相似度 ``score`` 与比对覆盖度 ``coverage``；额外召回路（序列 k-mer /
向量 KNN / 属性重叠等）由调用方以"按该路相关性从高到低排好的 target_accession 列表"经
``extra_channels`` 注入（对应 :class:`pkg.retrieval.hybrid.HybridRetriever` 的同名设计）。
"""

from __future__ import annotations

from pkg.retrieval import rrf
from pkg.structure.types import StructuralNeighbor


def rerank_neighbors(
    neighbors: list[StructuralNeighbor],
    *,
    rrf_k: int = 60,
    extra_channels: list[list[str]] | None = None,
) -> list[tuple[StructuralNeighbor, float]]:
    """RRF 融合 ``[按 score 排, 按 coverage 排, *extra_channels]`` → ``[(neighbor, fused_score)]`` 降序。

    同分时回退到结构 ``score`` 作稳定次序。``neighbors`` 为空时返回空列表。
    """
    if not neighbors:
        return []
    by_score = [
        n.target_accession
        for n in sorted(neighbors, key=lambda n: (n.score, n.coverage), reverse=True)
    ]
    by_coverage = [
        n.target_accession
        for n in sorted(neighbors, key=lambda n: (n.coverage, n.score), reverse=True)
    ]
    channels = [by_score, by_coverage, *(extra_channels or [])]
    fused = dict(rrf(channels, k=rrf_k))
    ranked = sorted(
        neighbors,
        key=lambda n: (fused.get(n.target_accession, 0.0), n.score),
        reverse=True,
    )
    return [(n, fused.get(n.target_accession, 0.0)) for n in ranked]


__all__ = ["rerank_neighbors"]
