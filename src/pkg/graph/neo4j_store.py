"""知识图谱端口的 Neo4j 实现（L3）。

实现 :class:`pkg.graph.port.GraphStore`：节点/边经 ``MERGE`` 幂等写入，遍历经
参数化 ``MATCH`` 读出。Neo4j 属性只能存基元/基元数组，故 ``mysql_ref`` 与完整
``properties`` 以 JSON 字符串落库（``mysql_ref`` / ``props_json``），读回时反序列化；
``evidence_level``/``score``/``log2fc`` 等查询用标量另行提升为顶层属性。

注：本类纯代码可推进、可对 Cypher 形状做结构测试；**真正连一个 Neo4j 实例**属于外部依赖
（实施清单 B 组），那步晚点接。Cypher 的语义对错需真库做集成测试，此处不覆盖。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

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

# Neo4j 属性里另行提升为顶层标量的 key（便于按值过滤/排序）。
_SCALAR_PROP_KEYS = (
    "name",
    "evidence_level",
    "score",
    "coverage",
    "rank",
    "fused_score",
    "fusion_rank",
    "support_channel_count",
    "log2fc",
    "direction",
    "is_differential",
    "q_value",
)


def _scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def _node_row(node: GraphNode) -> dict[str, Any]:
    props: dict[str, Any] = {
        "scope": node.scope.value,
        "experiment_id": node.experiment_id,
        "mysql_ref": json.dumps(node.mysql_ref, ensure_ascii=False, sort_keys=True),
        "props_json": json.dumps(node.properties, ensure_ascii=False, sort_keys=True),
    }
    for prop_key in _SCALAR_PROP_KEYS:
        if prop_key in node.properties and _scalar(node.properties[prop_key]):
            props[prop_key] = node.properties[prop_key]
    return {"key": node.key, "props": props}


def _edge_row(edge: GraphEdge) -> dict[str, Any]:
    props: dict[str, Any] = {
        "scope": edge.scope.value,
        "experiment_id": edge.experiment_id,
        "props_json": json.dumps(edge.properties, ensure_ascii=False, sort_keys=True),
    }
    for prop_key in _SCALAR_PROP_KEYS:
        if prop_key in edge.properties and _scalar(edge.properties[prop_key]):
            props[prop_key] = edge.properties[prop_key]
    return {"key": edge.key, "start_key": edge.start.key, "end_key": edge.end.key, "props": props}


def _to_node(label: NodeLabel, data: dict[str, Any]) -> GraphNode:
    scope = GraphScope(data.get("scope", GraphScope.GENERAL.value))
    return GraphNode(
        label=label,
        key=data["key"],
        scope=scope,
        experiment_id=data.get("experiment_id"),
        properties=json.loads(data.get("props_json") or "{}"),
        mysql_ref=json.loads(data.get("mysql_ref") or "{}"),
    )


def _to_edge(
    edge_type: EdgeType, start: NodeRef, end: NodeRef, data: dict[str, Any]
) -> GraphEdge:
    scope = GraphScope(data.get("scope", GraphScope.GENERAL.value))
    return GraphEdge(
        type=edge_type,
        start=start,
        end=end,
        key=data["key"],
        scope=scope,
        experiment_id=data.get("experiment_id"),
        properties=json.loads(data.get("props_json") or "{}"),
    )


class Neo4jGraphStore:
    """:class:`pkg.graph.port.GraphStore` 的 Neo4j 实现。"""

    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j") -> None:
        from neo4j import GraphDatabase  # 延迟加载：无 Neo4j 部署也能 import 本模块

        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._database = database

    def close(self) -> None:
        self._driver.close()

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        with self._driver.session(database=self._database) as session:
            return session.run(query, **params).data()

    # ---- schema：每个 label 的 key 唯一约束 ----
    def initialize_schema(self) -> None:
        for label in NodeLabel:
            self.run(
                f"CREATE CONSTRAINT kg_{label.value.lower()}_key IF NOT EXISTS "
                f"FOR (n:{label.value}) REQUIRE n.key IS UNIQUE"
            )

    # ---- 写入（按 label / (type,start,end) 分组，因 Cypher 不能参数化 label/relType）----
    def upsert_nodes(self, nodes: Sequence[GraphNode]) -> int:
        by_label: dict[NodeLabel, list[dict[str, Any]]] = {}
        for node in nodes:
            by_label.setdefault(node.label, []).append(_node_row(node))
        for label, rows in by_label.items():
            self.run(
                f"UNWIND $rows AS row "
                f"MERGE (n:{label.value} {{key: row.key}}) "
                f"SET n += row.props",
                rows=rows,
            )
        return len(nodes)

    def upsert_edges(self, edges: Sequence[GraphEdge]) -> int:
        by_shape: dict[tuple[EdgeType, NodeLabel, NodeLabel], list[dict[str, Any]]] = {}
        for edge in edges:
            by_shape.setdefault((edge.type, edge.start.label, edge.end.label), []).append(
                _edge_row(edge)
            )
        for (etype, start_label, end_label), rows in by_shape.items():
            self.run(
                f"UNWIND $rows AS row "
                f"MATCH (a:{start_label.value} {{key: row.start_key}}) "
                f"MATCH (b:{end_label.value} {{key: row.end_key}}) "
                f"MERGE (a)-[r:{etype.value} {{key: row.key}}]->(b) "
                f"SET r += row.props",
                rows=rows,
            )
        return len(edges)

    # ---- 查询 ----
    def get_node(self, label: NodeLabel, key: str) -> GraphNode | None:
        rows = self.run(
            f"MATCH (n:{label.value} {{key: $key}}) RETURN n{{.*}} AS n", key=key
        )
        return _to_node(label, rows[0]["n"]) if rows else None

    def neighbors(
        self,
        ref: NodeRef,
        edge_type: EdgeType,
        *,
        direction: Direction = Direction.OUT,
    ) -> list[GraphEdge]:
        if direction is Direction.OUT:
            pattern = (
                f"(a:{ref.label.value} {{key: $key}})-[r:{edge_type.value}]->(b)"
            )
        elif direction is Direction.IN:
            pattern = (
                f"(b)-[r:{edge_type.value}]->(a:{ref.label.value} {{key: $key}})"
            )
        else:
            pattern = (
                f"(a:{ref.label.value} {{key: $key}})-[r:{edge_type.value}]-(b)"
            )
        rows = self.run(
            f"MATCH {pattern} "
            f"RETURN r{{.*}} AS r, a.key AS a_key, labels(a)[0] AS a_label, "
            f"b.key AS b_key, labels(b)[0] AS b_label "
            f"ORDER BY r.key",
            key=ref.key,
        )
        out: list[GraphEdge] = []
        for row in rows:
            start = NodeRef(NodeLabel(row["a_label"]), row["a_key"])
            end = NodeRef(NodeLabel(row["b_label"]), row["b_key"])
            if direction is Direction.IN:  # 模式里 a 是被指向的一端，需翻转回真实方向
                start, end = end, start
            out.append(_to_edge(edge_type, start, end, row["r"]))
        return out

    def protein_diseases(
        self, accession: str, *, experiment_id: str | None = None
    ) -> list[DiseaseLink]:
        links: list[DiseaseLink] = []

        # 基因结论：Protein -(ENCODED_BY)-> Gene -(ASSOCIATED_WITH)-> Disease
        for row in self.run(
            "MATCH (p:Protein {key: $acc})-[:ENCODED_BY]->(g:Gene)"
            "-[r:ASSOCIATED_WITH]->(d:Disease) "
            "RETURN g.key AS gene, d.key AS disease, d.name AS name, "
            "r.evidence_level AS level, r.key AS edge_key ORDER BY r.key",
            acc=accession,
        ):
            links.append(
                DiseaseLink(
                    disease_key=row["disease"],
                    disease_name=row.get("name") or "",
                    evidence_level=row.get("level") or "",
                    via=f"gene:{row['gene']}",
                    edge_key=row["edge_key"],
                )
            )

        # 蛋白级假说：Protein -(ASSOCIATED_WITH)-> Disease（按实验工作区过滤）
        for row in self.run(
            "MATCH (p:Protein {key: $acc})-[r:ASSOCIATED_WITH]->(d:Disease) "
            "WHERE $exp IS NULL OR r.experiment_id = $exp "
            "RETURN d.key AS disease, d.name AS name, r.evidence_level AS level, "
            "r.key AS edge_key ORDER BY r.key",
            acc=accession,
            exp=experiment_id,
        ):
            links.append(
                DiseaseLink(
                    disease_key=row["disease"],
                    disease_name=row.get("name") or "",
                    evidence_level=row.get("level") or "",
                    via="protein",
                    edge_key=row["edge_key"],
                )
            )

        return sorted(links, key=lambda link: (link.disease_key, link.via, link.edge_key))

    def drop_experiment(self, experiment_id: str) -> int:
        removed = 0
        # 先删实验作用域的边（含 general 端点之间的边，如蛋白→疾病假说、蛋白→分组差异）
        rows = self.run(
            "MATCH ()-[r {scope: 'EXPERIMENT', experiment_id: $exp}]->() "
            "WITH r, count(*) AS _ DELETE r RETURN count(*) AS n",
            exp=experiment_id,
        )
        removed += rows[0]["n"] if rows else 0
        # 再删实验作用域的节点（DETACH 清掉残余关系）
        rows = self.run(
            "MATCH (n {scope: 'EXPERIMENT', experiment_id: $exp}) "
            "WITH n, count(*) AS _ DETACH DELETE n RETURN count(*) AS n",
            exp=experiment_id,
        )
        removed += rows[0]["n"] if rows else 0
        return removed

    def count_nodes(
        self,
        *,
        scope: GraphScope | None = None,
        label: NodeLabel | None = None,
        experiment_id: str | None = None,
    ) -> int:
        label_clause = f":{label.value}" if label else ""
        rows = self.run(
            f"MATCH (n{label_clause}) "
            f"WHERE ($scope IS NULL OR n.scope = $scope) "
            f"AND ($exp IS NULL OR n.experiment_id = $exp) "
            f"RETURN count(n) AS n",
            scope=scope.value if scope else None,
            exp=experiment_id,
        )
        return rows[0]["n"] if rows else 0

    def count_edges(
        self,
        *,
        scope: GraphScope | None = None,
        edge_type: EdgeType | None = None,
        experiment_id: str | None = None,
    ) -> int:
        type_clause = f":{edge_type.value}" if edge_type else ""
        rows = self.run(
            f"MATCH ()-[r{type_clause}]->() "
            f"WHERE ($scope IS NULL OR r.scope = $scope) "
            f"AND ($exp IS NULL OR r.experiment_id = $exp) "
            f"RETURN count(r) AS n",
            scope=scope.value if scope else None,
            exp=experiment_id,
        )
        return rows[0]["n"] if rows else 0


# ---------------- 进程内单例（对应旧 store 的 get_graph_store，但走新端口）----------------
_store: Neo4jGraphStore | None = None


def get_kg_store() -> Neo4jGraphStore:
    """返回新版双节点知识图谱 store 单例（按 ``PTAGENT_GRAPH__*`` 配置连库）。"""

    global _store
    if _store is None:
        from config.graph_settings import get_graph_settings

        settings = get_graph_settings()
        _store = Neo4jGraphStore(
            settings.uri, settings.user, settings.password, settings.database
        )
        _store.initialize_schema()
    return _store


__all__ = ["Neo4jGraphStore", "get_kg_store"]
