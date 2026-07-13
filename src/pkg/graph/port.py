"""知识图谱端口（L3）与确定性内存实现。

应用层只依赖 :class:`GraphStore` 协议；:class:`pkg.graph.neo4j_store.Neo4jGraphStore`
是正式实现，测试/开发可用 :class:`InMemoryGraphStore`。所有图访问经过这里，
业务服务不直绑 Cypher（§7.1）。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pkg.graph.model import (
    Direction,
    DiseaseLink,
    EdgeType,
    GraphEdge,
    GraphNode,
    GraphScope,
    NodeLabel,
    NodeRef,
)
from pkg.graph.identity import canonical_protein_key


@runtime_checkable
class GraphStore(Protocol):
    """两层知识图谱的存取端口。"""

    def initialize_schema(self) -> None:
        """幂等地准备约束/索引；内存实现为 no-op。"""
        ...

    def upsert_nodes(self, nodes: Sequence[GraphNode]) -> int:
        """按 (label, key) 幂等 upsert，合并 properties/mysql_ref；返回处理条数。"""
        ...

    def upsert_edges(self, edges: Sequence[GraphEdge]) -> int:
        """按 (type, key) 幂等 upsert，合并 properties；返回处理条数。"""
        ...

    def replace_experiment_projection(
        self,
        experiment_id: str,
        nodes: Sequence[GraphNode],
        edges: Sequence[GraphEdge],
    ) -> dict[str, int]:
        """Atomically replace one experiment workspace and upsert its GENERAL facts."""
        ...

    def get_node(self, label: NodeLabel, key: str) -> GraphNode | None: ...

    def neighbors(
        self,
        ref: NodeRef,
        edge_type: EdgeType,
        *,
        direction: Direction = Direction.OUT,
        experiment_id: str | None = None,
    ) -> list[GraphEdge]:
        """一跳遍历：返回与 ``ref`` 相连、类型为 ``edge_type`` 的边（按 key 排序）。"""
        ...

    def protein_diseases(
        self, accession: str, *, experiment_id: str
    ) -> list[DiseaseLink]:
        """从蛋白走到疾病：基因结论（ENCODED_BY→ASSOCIATED_WITH）+ 蛋白级假说。

        给定 ``experiment_id`` 时，蛋白级假说只取该实验工作区的；通用 KG 的基因结论始终包含。
        """
        ...

    def drop_experiment(self, experiment_id: str) -> int:
        """删除某实验工作区（仅 EXPERIMENT 作用域的节点+边），返回删除条数；不动通用 KG。"""
        ...

    def count_nodes(
        self,
        *,
        scope: GraphScope | None = None,
        label: NodeLabel | None = None,
        experiment_id: str | None = None,
    ) -> int: ...

    def count_edges(
        self,
        *,
        scope: GraphScope | None = None,
        edge_type: EdgeType | None = None,
        experiment_id: str | None = None,
    ) -> int: ...

    def close(self) -> None: ...


class InMemoryGraphStore:
    """确定性的测试/开发实现，不作为生产图库。"""

    def __init__(self) -> None:
        self._nodes: dict[tuple[NodeLabel, str], GraphNode] = {}
        self._edges: dict[tuple[EdgeType, str], GraphEdge] = {}

    def initialize_schema(self) -> None:
        return None

    def close(self) -> None:
        return None

    # ---- 写入（幂等合并）----
    def upsert_nodes(self, nodes: Sequence[GraphNode]) -> int:
        for node in nodes:
            ident = (node.label, node.key)
            existing = self._nodes.get(ident)
            if existing is None:
                self._nodes[ident] = node
                continue
            self._nodes[ident] = GraphNode(
                label=node.label,
                key=node.key,
                scope=node.scope,
                experiment_id=node.experiment_id,
                properties={**existing.properties, **node.properties},
                mysql_ref={**existing.mysql_ref, **node.mysql_ref},
            )
        return len(nodes)

    def upsert_edges(self, edges: Sequence[GraphEdge]) -> int:
        for edge in edges:
            ident = (edge.type, edge.key)
            existing = self._edges.get(ident)
            if existing is None:
                self._edges[ident] = edge
                continue
            self._edges[ident] = GraphEdge(
                type=edge.type,
                start=edge.start,
                end=edge.end,
                key=edge.key,
                scope=edge.scope,
                experiment_id=edge.experiment_id,
                properties={**existing.properties, **edge.properties},
            )
        return len(edges)

    def replace_experiment_projection(
        self,
        experiment_id: str,
        nodes: Sequence[GraphNode],
        edges: Sequence[GraphEdge],
    ) -> dict[str, int]:
        _validate_projection_payload(experiment_id, nodes, edges)
        removed = self.drop_experiment(experiment_id)
        return {
            "removed": removed,
            "nodes": self.upsert_nodes(nodes),
            "edges": self.upsert_edges(edges),
        }

    # ---- 查询 ----
    def get_node(self, label: NodeLabel, key: str) -> GraphNode | None:
        return self._nodes.get((label, key))

    def neighbors(
        self,
        ref: NodeRef,
        edge_type: EdgeType,
        *,
        direction: Direction = Direction.OUT,
        experiment_id: str | None = None,
    ) -> list[GraphEdge]:
        out: list[GraphEdge] = []
        for edge in self._edges.values():
            if edge.type is not edge_type:
                continue
            if edge.scope is GraphScope.EXPERIMENT and edge.experiment_id != experiment_id:
                continue
            if direction is Direction.OUT and edge.start != ref:
                continue
            if direction is Direction.IN and edge.end != ref:
                continue
            if direction is Direction.BOTH and ref not in (edge.start, edge.end):
                continue
            out.append(edge)
        return sorted(out, key=lambda e: e.key)

    def protein_diseases(
        self, accession: str, *, experiment_id: str
    ) -> list[DiseaseLink]:
        protein = NodeRef(NodeLabel.PROTEIN, canonical_protein_key(accession))
        links: list[DiseaseLink] = []

        # 基因结论：Protein -(ENCODED_BY)-> Gene -(ASSOCIATED_WITH)-> Disease（通用 KG）
        for enc in self.neighbors(protein, EdgeType.ENCODED_BY, direction=Direction.OUT):
            gene_ref = enc.end
            gene = self._nodes.get((gene_ref.label, gene_ref.key))
            gene_symbol = (
                str(gene.properties.get("symbol") or gene_ref.key)
                if gene is not None
                else gene_ref.key
            )
            for assoc in self.neighbors(
                gene_ref, EdgeType.ASSOCIATED_WITH, direction=Direction.OUT
            ):
                disease = self._nodes.get((assoc.end.label, assoc.end.key))
                links.append(
                    DiseaseLink(
                        disease_key=assoc.end.key,
                        disease_name=str(disease.properties.get("name", "")) if disease else "",
                        evidence_level=str(assoc.properties.get("evidence_level", "")),
                        via=f"gene:{gene_symbol}",
                        edge_key=assoc.key,
                    )
                )

        # 蛋白级假说：Protein -(ASSOCIATED_WITH)-> Disease（实验工作区）
        for assoc in self.neighbors(
            protein,
            EdgeType.ASSOCIATED_WITH,
            direction=Direction.OUT,
            experiment_id=experiment_id,
        ):
            disease = self._nodes.get((assoc.end.label, assoc.end.key))
            links.append(
                DiseaseLink(
                    disease_key=assoc.end.key,
                    disease_name=str(disease.properties.get("name", "")) if disease else "",
                    evidence_level=str(assoc.properties.get("evidence_level", "")),
                    via="protein",
                    edge_key=assoc.key,
                )
            )

        return sorted(links, key=lambda link: (link.disease_key, link.via, link.edge_key))

    def drop_experiment(self, experiment_id: str) -> int:
        removed = 0
        for ident, edge in list(self._edges.items()):
            if edge.scope is GraphScope.EXPERIMENT and edge.experiment_id == experiment_id:
                del self._edges[ident]
                removed += 1
        for ident, node in list(self._nodes.items()):
            if node.scope is GraphScope.EXPERIMENT and node.experiment_id == experiment_id:
                del self._nodes[ident]
                removed += 1
        return removed

    def count_nodes(
        self,
        *,
        scope: GraphScope | None = None,
        label: NodeLabel | None = None,
        experiment_id: str | None = None,
    ) -> int:
        return sum(
            1
            for node in self._nodes.values()
            if (scope is None or node.scope is scope)
            and (label is None or node.label is label)
            and (experiment_id is None or node.experiment_id == experiment_id)
        )

    def count_edges(
        self,
        *,
        scope: GraphScope | None = None,
        edge_type: EdgeType | None = None,
        experiment_id: str | None = None,
    ) -> int:
        return sum(
            1
            for edge in self._edges.values()
            if (scope is None or edge.scope is scope)
            and (edge_type is None or edge.type is edge_type)
            and (experiment_id is None or edge.experiment_id == experiment_id)
        )


def _validate_projection_payload(
    experiment_id: str,
    nodes: Sequence[GraphNode],
    edges: Sequence[GraphEdge],
) -> None:
    node_refs = {node.ref for node in nodes}
    for node in nodes:
        if node.scope is GraphScope.EXPERIMENT and node.experiment_id != experiment_id:
            raise ValueError(
                f"experiment node {node.label.value}:{node.key} belongs to "
                f"{node.experiment_id}, expected {experiment_id}"
            )
    for edge in edges:
        if edge.scope is GraphScope.EXPERIMENT and edge.experiment_id != experiment_id:
            raise ValueError(
                f"experiment edge {edge.type.value}:{edge.key} belongs to "
                f"{edge.experiment_id}, expected {experiment_id}"
            )
        missing = [ref for ref in (edge.start, edge.end) if ref not in node_refs]
        if missing:
            rendered = ", ".join(f"{ref.label.value}:{ref.key}" for ref in missing)
            raise ValueError(f"edge {edge.type.value}:{edge.key} has missing nodes: {rendered}")


__all__ = ["GraphStore", "InMemoryGraphStore"]
