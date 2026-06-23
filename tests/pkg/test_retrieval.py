"""混合检索纯函数库测试：k-mer 召回 / RRF / 属性重叠 / rerank / HybridRetriever。"""
from __future__ import annotations

from pkg.retrieval import (
    HybridRetriever,
    KmerIndex,
    jaccard,
    overlap_recall,
    rerank,
    rrf,
    seq_identity,
)


def test_kmer_recall_ranks_by_shared_kmers() -> None:
    idx = KmerIndex({"a": "ABCDEF", "b": "ABCXYZ", "c": "QQQQQQ"}, k=3)
    out = idx.recall("ABCDEF", top_n=3)
    assert out[0] == "a"            # 完全相同 → 共享最多
    assert "b" in out              # 共享 ABC
    assert "c" not in out          # 无共享 3-mer，丢弃


def test_rrf_combines_ranks_and_drops_singletons_last() -> None:
    fused = rrf([["X", "Y", "Z"], ["Y", "X"]])
    ids = [i for i, _ in fused]
    assert set(ids) == {"X", "Y", "Z"}
    assert ids[-1] == "Z"          # 只出现在一路，排最后
    assert ids[0] in {"X", "Y"}    # 两路都靠前的优先


def test_overlap_recall_by_jaccard() -> None:
    assert jaccard({"a", "b"}, {"b", "c"}) == 1 / 3
    out = overlap_recall(
        {"GO:1", "GO:2"},
        {"x": {"GO:1"}, "y": {"GO:9"}, "z": {"GO:1", "GO:2"}},
    )
    assert out[0] == "z"           # 全重叠
    assert "y" not in out          # 零重叠丢弃


def test_rerank_orders_by_scorer() -> None:
    out = rerank("ABCDEF", ["ABCDEF", "ABCXYZ", "QQQ"], scorer=seq_identity, top_k=2)
    ids = [i for i, _ in out]
    assert ids[0] == "ABCDEF"      # 完全相同最高
    assert len(out) == 2


def test_hybrid_excludes_self_and_returns_topk() -> None:
    seqs = {"q": "PEPTIDEK", "n1": "PEPTIDER", "n2": "PEPTIDEN", "far": "ZZZZZZZZ"}
    attrs = {"q": {"GO:1"}, "n1": {"GO:1"}}        # n2/far 无属性
    r = HybridRetriever(seqs, attrs)
    out = r.neighbors("q", top_k=2)
    ids = [i for i, _ in out]
    assert "q" not in ids          # 不连自己
    assert len(ids) <= 2
    assert "n1" in ids             # 共享 k-mer + 属性
    assert "far" not in ids        # 无共享


def test_hybrid_dense_channel_injection() -> None:
    # 两串毫不相似(k-mer/属性都空)，靠注入的稠密通道把 a~b 连起来
    seqs = {"a": "AAAAAAAA", "b": "BBBBBBBB"}
    r = HybridRetriever(seqs)
    out = r.neighbors("a", top_k=1, extra_channels=[["b"]])
    assert [i for i, _ in out] == ["b"]
