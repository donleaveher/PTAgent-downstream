"""混合检索包：召回(k-mer/属性重叠) + RRF 融合 + rerank。纯函数，不依赖图/网络。"""
from pkg.retrieval.fusion import rrf
from pkg.retrieval.hybrid import HybridRetriever
from pkg.retrieval.recall import KmerIndex, jaccard, kmers, overlap_recall
from pkg.retrieval.rerank import Scorer, rerank, seq_identity

__all__ = [
    "kmers",
    "KmerIndex",
    "jaccard",
    "overlap_recall",
    "rrf",
    "seq_identity",
    "rerank",
    "Scorer",
    "HybridRetriever",
]
