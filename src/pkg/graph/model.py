"""本次实验 KG / 通用 KG 的图模型（L3）。

把散在 MySQL 的事实投影成可遍历的双节点图（Q3：Protein/Gene/Disease + Group），
节点/边只带 canonical key + 轻量属性 + ``mysql_ref``（重数据留在 MySQL，Q5），
统一经 :class:`pkg.graph.port.GraphStore` 端口访问，业务不直绑 Cypher。

两层（Q4）：

- 通用 KG（``GENERAL``）：跨实验复用的"字典"——Protein/Gene/Disease 与
  ``ENCODED_BY``、基因→疾病 ``ASSOCIATED_WITH(CONCLUSION)``、``STRUCTURAL_NEIGHBOR``。
- 本次实验 KG（``EXPERIMENT``，带 ``experiment_id``）：这次的"故事"——Group、
  ``DIFFERENTIAL``、以及蛋白级疾病 ``ASSOCIATED_WITH(HYPOTHESIS)``。
  删工作区（:meth:`GraphStore.drop_experiment`）只清 ``EXPERIMENT`` 作用域，不动通用 KG。

注：本模块与同包的旧 ``types.py``/``store.py``（PSM/肽序列 KNN，§13 待 deprecate）相互独立。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GraphScope(str, Enum):
    """节点/边的所属层。"""

    GENERAL = "GENERAL"        # 跨实验稳定事实（通用 KG）
    EXPERIMENT = "EXPERIMENT"  # 本次实验判断（实验工作区，须带 experiment_id）


class NodeLabel(str, Enum):
    PROTEIN = "Protein"
    GENE = "Gene"
    DISEASE = "Disease"
    GROUP = "Group"


class EdgeType(str, Enum):
    ENCODED_BY = "ENCODED_BY"                      # (Protein)->(Gene)，缝合双节点（Q3）
    ASSOCIATED_WITH = "ASSOCIATED_WITH"           # (Gene|Protein)->(Disease)，带 evidence_level
    STRUCTURAL_NEIGHBOR = "STRUCTURAL_NEIGHBOR"   # (Protein)->(Protein)，带 score（Foldseek 假说）
    DIFFERENTIAL = "DIFFERENTIAL"                 # (Protein)->(Group)，带 log2fc（L2 差异）


class Direction(str, Enum):
    """一跳遍历方向。"""

    OUT = "OUT"    # 从给定节点出发
    IN = "IN"      # 指向给定节点
    BOTH = "BOTH"


@dataclass(frozen=True)
class NodeRef:
    """图节点的身份（label + canonical key），用于指定边的两端。"""

    label: NodeLabel
    key: str


@dataclass(frozen=True)
class GraphNode:
    """一个图节点。``key`` 为 canonical id：accession / gene symbol / disease_id / group_key。"""

    label: NodeLabel
    key: str
    scope: GraphScope = GraphScope.GENERAL
    experiment_id: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    mysql_ref: dict[str, Any] = field(default_factory=dict)  # 指回 MySQL（Q5：重数据不进图）

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError(f"{self.label.value} node requires a non-empty key")
        if self.scope is GraphScope.EXPERIMENT and not self.experiment_id:
            raise ValueError(
                f"EXPERIMENT-scoped node {self.label.value}:{self.key} requires experiment_id"
            )
        if self.scope is GraphScope.GENERAL and self.experiment_id is not None:
            raise ValueError(
                f"GENERAL-scoped node {self.label.value}:{self.key} must not carry experiment_id"
            )

    @property
    def ref(self) -> NodeRef:
        return NodeRef(self.label, self.key)


@dataclass(frozen=True)
class GraphEdge:
    """一条有向边。``key`` 为稳定关系键（幂等 MERGE），通常复用 MySQL 稳定 ID。"""

    type: EdgeType
    start: NodeRef
    end: NodeRef
    key: str
    scope: GraphScope = GraphScope.GENERAL
    experiment_id: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError(f"{self.type.value} edge requires a non-empty key")
        if self.scope is GraphScope.EXPERIMENT and not self.experiment_id:
            raise ValueError(
                f"EXPERIMENT-scoped {self.type.value} edge {self.key} requires experiment_id"
            )
        if self.scope is GraphScope.GENERAL and self.experiment_id is not None:
            raise ValueError(
                f"GENERAL-scoped {self.type.value} edge {self.key} must not carry experiment_id"
            )


@dataclass(frozen=True)
class DiseaseLink:
    """从蛋白走到疾病的一条可读结果（跨 ENCODED_BY 缝合 + 直接假说，统一返回形态）。"""

    disease_key: str
    disease_name: str
    evidence_level: str  # CONCLUSION / HYPOTHESIS / REFUTED
    via: str             # "gene:<symbol>"（基因结论）或 "protein"（蛋白级假说）
    edge_key: str


__all__ = [
    "Direction",
    "DiseaseLink",
    "EdgeType",
    "GraphEdge",
    "GraphNode",
    "GraphScope",
    "NodeLabel",
    "NodeRef",
]
