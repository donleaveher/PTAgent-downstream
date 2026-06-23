"""阶段3：查库归属——de novo 肽序列 → 比对蛋白库 → 写 BELONGS_TO + novelty 标注。

镜像 :mod:`application.graph.embed_knn`：从图读还没查库的肽 → ``pkg.protein_db`` 查 →
回写 ``merge_pep_prot``(命中边) + ``write_lookup``(命中与否，含 novel)。
幂等：只查 ``db_searched`` 还没标过的肽(``Q_UNSEARCHED``)；重跑安全。

不在 materializer 里做：materializer 只解工具产物、建主干；查库是我们拿肽去 FASTA 找，
是一步独立富集(和 embed/knn 同构)，不耦合 per-run 入图。
"""
from __future__ import annotations

import logging
from typing import Any

from pkg.graph import get_graph_store
from pkg.graph.types import PepLookupRow, PepProtRow
from pkg.protein_db import ProteinDB, get_protein_db

logger = logging.getLogger(__name__)


def assign_proteins(db: ProteinDB | None = None) -> dict[str, Any]:
    """对所有还没查库的肽做归属：写命中边 + novelty 标注。返回计数。"""
    g = get_graph_store()
    pdb = db or get_protein_db()
    todo = g.list_unsearched_peptides()           # [{peptidoform, seq}]
    if not todo:
        logger.info("[assign] 没有待查库的肽")
        return {"searched": 0, "hits": 0, "novel": 0}

    pep_prot: list[PepProtRow] = []
    lookup: list[PepLookupRow] = []
    novel = 0
    for t in todo:
        hits = pdb.lookup(t["seq"])
        for h in hits:
            pep_prot.append({
                "peptidoform": t["peptidoform"],
                "accession": h["accession"],
                "description": h["description"],
            })
        if not hits:
            novel += 1
        lookup.append({
            "peptidoform": t["peptidoform"],
            "db_hit": bool(hits),
            "db_name": pdb.name,
            "db_version": pdb.version,
        })

    g.merge_pep_prot(pep_prot)        # 只对命中的肽建 BELONGS_TO
    g.write_lookup(lookup)            # 命中与否都标(novel = db_hit false)
    logger.info("[assign] 查库 %d 肽：命中边 %d，novel %d", len(todo), len(pep_prot), novel)
    return {"searched": len(todo), "hits": len(pep_prot), "novel": novel}


__all__ = ["assign_proteins"]
