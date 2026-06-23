"""阶段6：假说生成——对(novel)肽，把相似邻居母蛋白的属性取共识 → 预测属性 = 假说。

读图：肽的 ``SIMILAR_TO`` 邻居 + 每个邻居母蛋白的 go/ec/interpro(**按 accession 分组**) →
``transfer_annotations`` 取共识 → ``HypothesisRow`` 列表。假说**不入图**(瞬时使用，喂阶段7/报告)。
"""
from __future__ import annotations

import logging
from typing import Any

from pkg.graph import get_graph_store
from pkg.graph.types import HypothesisRow
from pkg.hypothesis import Neighbor, transfer_annotations

logger = logging.getLogger(__name__)


def _neighbors_from_rows(rows: list[dict[str, Any]]) -> list[Neighbor]:
    """把 Q_NEIGHBOR_ANNOTS 的行(proteins 是 map 列表)转成按 accession 分组的 Neighbor。"""
    neighbors: list[Neighbor] = []
    for r in rows:
        proteins: dict[str, dict[str, list[str]]] = {}
        for pr in (r.get("proteins") or []):
            proteins[pr["accession"]] = {
                "go": pr.get("go") or [],
                "ec": pr.get("ec") or [],
                "interpro": pr.get("interpro") or [],
            }
        neighbors.append({"id": r["id"], "score": r.get("score") or 0.0, "proteins": proteins})
    return neighbors


def hypothesize_peptide(
    peptidoform: str,
    *,
    min_confidence: float = 0.0,
    top_n: int | None = None,
) -> list[HypothesisRow]:
    """对一条肽生成假说(预测属性)。无邻居/无注释 → 空列表。"""
    g = get_graph_store()
    neighbors = _neighbors_from_rows(g.neighbor_annotations(peptidoform))
    preds = transfer_annotations(neighbors, min_confidence=min_confidence, top_n=top_n)
    return [
        {
            "peptidoform": peptidoform,
            "attr_type": p["attr_type"],
            "predicted": p["predicted"],
            "support": p["support"],        # [{neighbor, via:[accession,...]}]
            "confidence": p["confidence"],
        }
        for p in preds
    ]


def hypothesize_novel(
    *,
    min_confidence: float = 0.0,
    top_n: int | None = None,
) -> dict[str, Any]:
    """对所有 novel 肽批量生成假说(它们没自带属性，全靠邻居传递)。"""
    g = get_graph_store()
    novel = g.list_novel_peptides()                   # [{peptidoform, seq}]
    hypotheses: dict[str, list[HypothesisRow]] = {}
    for n in novel:
        h = hypothesize_peptide(
            n["peptidoform"], min_confidence=min_confidence, top_n=top_n
        )
        if h:
            hypotheses[n["peptidoform"]] = h
    logger.info("[hypo] novel %d 肽 → %d 个有假说", len(novel), len(hypotheses))
    return {
        "novel": len(novel),
        "with_hypotheses": len(hypotheses),
        "hypotheses": hypotheses,
    }


__all__ = ["hypothesize_peptide", "hypothesize_novel"]
