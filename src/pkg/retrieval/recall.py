"""召回通道：序列 k-mer(稀疏) + 属性集合重叠(Jaccard)。纯函数，不依赖图/网络/模型。"""
from __future__ import annotations


def kmers(seq: str, k: int = 3) -> set[str]:
    """序列 → k-mer 集合；长度不足 k 时退化成整串。"""
    if not seq:
        return set()
    if len(seq) <= k:
        return {seq}
    return {seq[i:i + k] for i in range(len(seq) - k + 1)}


class KmerIndex:
    """对语料按 k-mer 建索引；recall 按共享 k-mer 数排序(抓 embedding 漏的局部同源)。"""

    def __init__(self, corpus: dict[str, str], k: int = 3) -> None:
        self.k = k
        self._km: dict[str, set[str]] = {cid: kmers(s, k) for cid, s in corpus.items()}

    def recall(self, query_seq: str, top_n: int = 50) -> list[str]:
        q = kmers(query_seq, self.k)
        if not q:
            return []
        scored = [(cid, len(q & ks)) for cid, ks in self._km.items()]
        scored = [t for t in scored if t[1] > 0]                 # 无共享的不进候选
        scored.sort(key=lambda kv: (-kv[1], kv[0]))              # 分降序，id 升序定序
        return [cid for cid, _ in scored[:top_n]]


def jaccard(a: set[str], b: set[str]) -> float:
    u = len(a | b)
    return len(a & b) / u if u else 0.0


def overlap_recall(
    query_set: set[str],
    corpus_sets: dict[str, set[str]],
    top_n: int = 50,
) -> list[str]:
    """属性集合(go/ec/interpro)重叠召回：按 Jaccard 排序，零重叠丢弃。"""
    if not query_set:
        return []
    scored = [(cid, jaccard(query_set, s)) for cid, s in corpus_sets.items()]
    scored = [t for t in scored if t[1] > 0]
    scored.sort(key=lambda kv: (-kv[1], kv[0]))
    return [cid for cid, _ in scored[:top_n]]
