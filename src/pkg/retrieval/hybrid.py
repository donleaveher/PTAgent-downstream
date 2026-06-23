"""混合检索编排（纯内存、可测）：序列+属性召回 → RRF 融合 → rerank → top-k。

稠密(ESM/gds.knn)那一路不在这里算，由调用方以"每条查询的预排候选"经 ``extra_channels`` 注入，
当作 RRF 的额外一路——对应 spec §7+ "gds.knn 仅作稠密召回一路"。
"""
from __future__ import annotations

from pkg.retrieval.fusion import rrf
from pkg.retrieval.recall import KmerIndex, overlap_recall
from pkg.retrieval.rerank import Scorer, rerank, seq_identity


class HybridRetriever:
    def __init__(
        self,
        seqs: dict[str, str],
        attrs: dict[str, set[str]] | None = None,
        *,
        k_kmer: int = 3,
        rrf_k: int = 60,
        recall_n: int = 50,
        scorer: Scorer = seq_identity,
    ) -> None:
        self.seqs = seqs
        self.attrs = attrs or {}
        self._kindex = KmerIndex(seqs, k=k_kmer)
        self.rrf_k = rrf_k
        self.recall_n = recall_n
        self.scorer = scorer

    def neighbors(
        self,
        qid: str,
        top_k: int = 5,
        extra_channels: list[list[str]] | None = None,
    ) -> list[tuple[str, float]]:
        """返回 qid 的 top-k 近邻 [(id, rerank 分)]，已排除自身。"""
        qseq = self.seqs[qid]
        channels: list[list[str]] = [
            [i for i in self._kindex.recall(qseq, self.recall_n) if i != qid]
        ]
        qattr = self.attrs.get(qid)
        if qattr:
            channels.append(
                [i for i in overlap_recall(qattr, self.attrs, self.recall_n) if i != qid]
            )
        for ch in (extra_channels or []):
            channels.append([i for i in ch if i != qid])

        fused = rrf(channels, k=self.rrf_k)
        cand = [cid for cid, _ in fused]
        return rerank(qseq, cand, self.scorer, top_k=top_k)
