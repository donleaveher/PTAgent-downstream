"""基因-疾病关联的标准事实与数据源协议。

对标 `pkg.annotation.knowledge`：annotation 是蛋白属性（挂蛋白级），
本模块是疾病关联（挂基因级，Q3 双节点）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class GeneDiseaseFact:
    """CTD 等直接数据源返回的一条可溯源 基因-疾病 关联（直接证据级）。"""

    gene: str
    disease_id: str  # 如 MESH:D002545 / OMIM:601367
    disease_name: str
    evidence_type: str  # CTD DirectEvidence，如 marker/mechanism、therapeutic
    relation_id: str | None = None  # 稳定引用，如 "<gene_id>|<disease_id>"
    pubmed_ids: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class GeneDiseaseSource(Protocol):
    name: str
    version: str

    def fetch(self, genes: list[str]) -> dict[str, list[GeneDiseaseFact]]:
        """按基因符号批量返回直接证据级 基因-疾病 关联；未命中的基因可不出现在结果中。"""

        ...


__all__ = ["GeneDiseaseFact", "GeneDiseaseSource"]
