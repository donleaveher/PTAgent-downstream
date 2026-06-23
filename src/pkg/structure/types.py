"""结构相似检索的标准结果与数据源协议。

KNN = **结构相似**（Foldseek over AlphaFold DB），非序列、非网络。物种无关，
因此一个大鼠蛋白的结构近邻天然包含人源蛋白——这是跨物种桥的底座。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class StructuralNeighbor:
    """一条结构近邻：query 蛋白 → target 近邻蛋白（按结构相似）。"""

    query_accession: str
    target_accession: str
    score: float  # 结构相似度（Foldseek prob，0-1，越大越像）
    coverage: float  # 比对覆盖度（tcov）
    rank: int = 0  # 在该 query 近邻中的名次（1 = 最相似）
    taxon_id: int | None = None  # 近邻所属物种（如人 9606）——跨物种桥用
    taxon_name: str = ""
    relation_id: str = ""  # 稳定关系键（query->target），供 STRUCTURAL_NEIGHBOR 图投影
    provenance: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class StructureSearchProvider(Protocol):
    name: str
    version: str

    def search(
        self, accessions: list[str], *, top_k: int | None = None
    ) -> dict[str, list[StructuralNeighbor]]:
        """按 accession 批量返回结构近邻（已排序、去自身、过阈值）；未命中的可不出现。"""

        ...


__all__ = ["StructuralNeighbor", "StructureSearchProvider"]
