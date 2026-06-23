"""序列 embedding 能力包。

对外只暴露接口 :class:`SequenceEncoder` 与工厂 :func:`get_encoder`；
上层（pkg/graph 写节点属性、application/graph 跑 gds.knn）只依赖这两者，
换实现（k-mer 占位 → ESM → 外部 MCP）时上层不动。
"""
from __future__ import annotations

from pkg.embedding.base import STANDARD_AA, SequenceEncoder, normalize_sequence
from pkg.embedding.kmer_encoder import KmerEncoder

# 进程内单例（对应 data_plane.get_data_plane_store / graph.get_graph_store 的惯例）
_encoder: SequenceEncoder | None = None


def get_encoder() -> SequenceEncoder:
    """返回进程内默认序列编码器。

    当前为 k-mer 占位实现（纯 numpy，无重依赖）；后续切换 ESM 等只改此处。
    """
    global _encoder
    if _encoder is None:
        _encoder = KmerEncoder(k=2)
    return _encoder


__all__ = [
    "SequenceEncoder",
    "KmerEncoder",
    "get_encoder",
    "normalize_sequence",
    "STANDARD_AA",
]
