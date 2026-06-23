"""阶段3.5：蛋白注释富集——按 accession 取 go/ec/interpro 写成 Protein 节点属性。

镜像 :mod:`application.graph.db_assign` / ``embed_knn``：从图读未富集蛋白 →
``pkg.annotation`` 批量取 → 回写 ``write_annotations``。
幂等：只补 ``annot_version`` 还没标的蛋白(``Q_UNANNOTATED``)；源里查不到的留到下次(源更新后可再得)。
"""
from __future__ import annotations

import logging
from typing import Any

from pkg.annotation import AnnotationSource, get_annotation_source
from pkg.graph import get_graph_store
from pkg.graph.types import ProtAnnotRow

logger = logging.getLogger(__name__)


def enrich_proteins(source: AnnotationSource | None = None) -> dict[str, Any]:
    """对所有还没富集的蛋白补注释属性。返回计数。"""
    g = get_graph_store()
    src = source or get_annotation_source()
    todo = g.list_unannotated_proteins()          # [{accession}]
    if not todo:
        logger.info("[enrich] 没有待富集的蛋白")
        return {"unannotated": 0, "enriched": 0}

    accs = sorted({t["accession"] for t in todo})
    annots = src.fetch(accs)                       # {acc: {go, ec, interpro}}
    rows: list[ProtAnnotRow] = [
        {
            "accession": a,
            "go": annots[a].get("go", []),
            "ec": annots[a].get("ec", []),
            "interpro": annots[a].get("interpro", []),
            "source": src.name,
            "version": src.version,
        }
        for a in accs
        if a in annots                             # 源里没有的不写，留到下次(源更新后可再得)
    ]
    n = g.write_annotations(rows)
    logger.info("[enrich] 富集 %d/%d 蛋白（源=%s@%s）", n, len(accs), src.name, src.version)
    return {"unannotated": len(accs), "enriched": n}


__all__ = ["enrich_proteins"]
