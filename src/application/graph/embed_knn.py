"""阶段 5：序列 embedding → gds.knn → SIMILAR_TO 相似边。

镜像 materializer：从图谱读裸序列 → 调 pkg.embedding 编码 → 写回节点属性
→ 跑 gds.knn 生成 ``(Peptide)-[:SIMILAR_TO {score}]->(Peptide)``。
幂等：只补还没向量的肽；KNN 在稳定的 embedding 上重跑结果一致。
"""
from __future__ import annotations

import logging
from typing import Any

from pkg.embedding import SequenceEncoder, get_encoder
from pkg.graph import get_graph_store
from pkg.graph.types import EmbeddingRow
from pkg.retrieval import HybridRetriever

logger = logging.getLogger(__name__)


def embed_peptides(encoder: SequenceEncoder | None = None) -> int:
    """给所有还没 embedding 的 Peptide 算向量并写回。返回新写入条数。"""
    g = get_graph_store()
    enc = encoder or get_encoder()
    todo = g.list_unembedded()                   # [{peptidoform, seq}]
    if not todo:
        logger.info("[embed] 没有待编码的肽")
        return 0
    seqs = sorted({t["seq"] for t in todo})       # 同裸序列只过一次模型
    vecs = enc.encode(seqs)
    seq2vec = dict(zip(seqs, vecs))
    rows: list[EmbeddingRow] = [
        {"peptidoform": t["peptidoform"], "embedding": seq2vec[t["seq"]]}
        for t in todo
    ]
    n = g.write_embeddings(rows)
    logger.info("[embed] 写入 %d 条肽 embedding（dim=%d）", n, enc.dim)
    return n


def build_similarity(k: int = 5, cutoff: float = 0.8) -> None:
    """跑 gds.knn，按 embedding 生成 SIMILAR_TO 相似边（需 Neo4j 装 GDS 插件）。"""
    get_graph_store().run_knn(k=k, cutoff=cutoff)
    logger.info("[knn] SIMILAR_TO 已生成（topK=%d, cutoff=%.2f）", k, cutoff)


def embed_and_knn(
    k: int = 5,
    cutoff: float = 0.8,
    encoder: SequenceEncoder | None = None,
) -> dict[str, Any]:
    """阶段 5 一键编排：先补 embedding，再建相似边。"""
    n = embed_peptides(encoder)
    build_similarity(k=k, cutoff=cutoff)
    return {"embedded": n, "k": k, "cutoff": cutoff}


def build_hybrid_similarity(
    k: int = 5,
    dense_neighbors: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """阶段5 混合检索：序列(k-mer)+属性重叠召回 → RRF 融合 → rerank → top-k SIMILAR_TO。

    稠密(ESM/gds.knn)那一路按需通过 ``dense_neighbors``（每条肽的预排候选）注入，
    当作 RRF 的额外一路；不传则只用序列+属性两路。融合/精排全在应用层（spec §7+）。
    """
    g = get_graph_store()
    corpus = g.peptide_corpus()                    # [{peptidoform, seq, attrs}]
    seqs = {c["peptidoform"]: c["seq"] for c in corpus}
    attrs = {c["peptidoform"]: set(c.get("attrs") or []) for c in corpus}
    retr = HybridRetriever(seqs, {pid: a for pid, a in attrs.items() if a})

    dn = dense_neighbors or {}
    pairs: list[dict[str, Any]] = []
    for qid in seqs:
        extra = [dn[qid]] if qid in dn else None
        for dst, score in retr.neighbors(qid, top_k=k, extra_channels=extra):
            pairs.append({"src": qid, "dst": dst, "score": round(float(score), 6)})

    n = g.write_similarity(pairs)
    logger.info("[hybrid] %d 肽 → %d 条 SIMILAR_TO 边（top-k=%d）", len(seqs), n, k)
    return {"queries": len(seqs), "edges": n}


__all__ = [
    "embed_peptides",
    "build_similarity",
    "embed_and_knn",
    "build_hybrid_similarity",
]
