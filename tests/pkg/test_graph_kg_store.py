"""L3 知识图谱模型 + GraphStore 端口契约测试（不连 Neo4j）。

内存实现走真实遍历逻辑；Neo4j 实现用记录器拦截 ``run``，验"发出去的 Cypher 形状"
（语义对错需真库集成测试，此处不覆盖）。
"""
from __future__ import annotations

from typing import Any

import pytest

from pkg.graph import (
    Direction,
    EdgeType,
    GraphEdge,
    GraphNode,
    GraphScope,
    GraphStore,
    InMemoryGraphStore,
    NodeLabel,
    NodeRef,
)
from pkg.graph.neo4j_store import Neo4jGraphStore


# ---------------- 模型不变量 ----------------
def test_experiment_scope_requires_experiment_id() -> None:
    with pytest.raises(ValueError):
        GraphNode(label=NodeLabel.GROUP, key="g1", scope=GraphScope.EXPERIMENT)
    with pytest.raises(ValueError):
        GraphEdge(
            type=EdgeType.DIFFERENTIAL,
            start=NodeRef(NodeLabel.PROTEIN, "P1"),
            end=NodeRef(NodeLabel.GROUP, "g1"),
            key="d1",
            scope=GraphScope.EXPERIMENT,
        )


def test_general_scope_rejects_experiment_id_and_empty_key() -> None:
    with pytest.raises(ValueError):
        GraphNode(label=NodeLabel.GENE, key="G1", experiment_id="exp1")
    with pytest.raises(ValueError):
        GraphNode(label=NodeLabel.GENE, key="")


# ---------------- 内存实现 ----------------
def test_inmemory_satisfies_port() -> None:
    assert isinstance(InMemoryGraphStore(), GraphStore)


def test_upsert_is_idempotent_and_merges_properties() -> None:
    store = InMemoryGraphStore()
    store.upsert_nodes([GraphNode(NodeLabel.PROTEIN, "P1", properties={"organism": "rat"})])
    store.upsert_nodes(
        [GraphNode(NodeLabel.PROTEIN, "P1", properties={"taxon_id": 10116})]
    )
    assert store.count_nodes() == 1
    node = store.get_node(NodeLabel.PROTEIN, "P1")
    assert node is not None
    assert node.properties == {"organism": "rat", "taxon_id": 10116}  # 合并而非覆盖

    edge = GraphEdge(
        EdgeType.ENCODED_BY,
        NodeRef(NodeLabel.PROTEIN, "P1"),
        NodeRef(NodeLabel.GENE, "G1"),
        key="P1|ENCODED_BY|G1",
    )
    store.upsert_edges([edge, edge])
    assert store.count_edges() == 1


def test_neighbors_directions() -> None:
    store = InMemoryGraphStore()
    store.upsert_edges(
        [
            GraphEdge(
                EdgeType.STRUCTURAL_NEIGHBOR,
                NodeRef(NodeLabel.PROTEIN, "P1"),
                NodeRef(NodeLabel.PROTEIN, "P2"),
                key="P1|SN|P2",
                properties={"score": 0.9},
            )
        ]
    )
    out = store.neighbors(
        NodeRef(NodeLabel.PROTEIN, "P1"), EdgeType.STRUCTURAL_NEIGHBOR, direction=Direction.OUT
    )
    assert [e.end.key for e in out] == ["P2"]
    assert store.neighbors(
        NodeRef(NodeLabel.PROTEIN, "P2"), EdgeType.STRUCTURAL_NEIGHBOR, direction=Direction.OUT
    ) == []
    in_edges = store.neighbors(
        NodeRef(NodeLabel.PROTEIN, "P2"), EdgeType.STRUCTURAL_NEIGHBOR, direction=Direction.IN
    )
    assert [e.start.key for e in in_edges] == ["P1"]
    assert (
        len(
            store.neighbors(
                NodeRef(NodeLabel.PROTEIN, "P2"),
                EdgeType.STRUCTURAL_NEIGHBOR,
                direction=Direction.BOTH,
            )
        )
        == 1
    )


def _seed_protein_disease(store: InMemoryGraphStore) -> None:
    store.upsert_nodes(
        [
            GraphNode(NodeLabel.PROTEIN, "P1"),
            GraphNode(NodeLabel.GENE, "G1"),
            GraphNode(NodeLabel.DISEASE, "D1", properties={"name": "DiseaseOne"}),
            GraphNode(NodeLabel.DISEASE, "D2", properties={"name": "DiseaseTwo"}),
        ]
    )
    store.upsert_edges(
        [
            GraphEdge(
                EdgeType.ENCODED_BY,
                NodeRef(NodeLabel.PROTEIN, "P1"),
                NodeRef(NodeLabel.GENE, "G1"),
                key="P1|ENCODED_BY|G1",
            ),
            GraphEdge(  # 基因结论（通用 KG）
                EdgeType.ASSOCIATED_WITH,
                NodeRef(NodeLabel.GENE, "G1"),
                NodeRef(NodeLabel.DISEASE, "D1"),
                key="a1",
                properties={"evidence_level": "CONCLUSION"},
            ),
            GraphEdge(  # 蛋白级假说（实验工作区）
                EdgeType.ASSOCIATED_WITH,
                NodeRef(NodeLabel.PROTEIN, "P1"),
                NodeRef(NodeLabel.DISEASE, "D2"),
                key="a2",
                scope=GraphScope.EXPERIMENT,
                experiment_id="exp1",
                properties={"evidence_level": "HYPOTHESIS"},
            ),
        ]
    )


def test_protein_diseases_crosses_gene_seam_and_separates_hypothesis() -> None:
    store = InMemoryGraphStore()
    _seed_protein_disease(store)

    links = store.protein_diseases("P1", experiment_id="exp1")
    by_disease = {link.disease_key: link for link in links}
    assert set(by_disease) == {"D1", "D2"}
    assert by_disease["D1"].evidence_level == "CONCLUSION"
    assert by_disease["D1"].via == "gene:G1"
    assert by_disease["D1"].disease_name == "DiseaseOne"
    assert by_disease["D2"].evidence_level == "HYPOTHESIS"
    assert by_disease["D2"].via == "protein"

    # 实验过滤：别的实验看不到本实验工作区的蛋白级假说，但仍能看到通用基因结论
    other = store.protein_diseases("P1", experiment_id="other")
    assert {link.disease_key for link in other} == {"D1"}


def test_drop_experiment_only_clears_workspace() -> None:
    store = InMemoryGraphStore()
    _seed_protein_disease(store)
    assert store.count_nodes(scope=GraphScope.GENERAL) == 4
    assert store.count_edges(scope=GraphScope.EXPERIMENT, experiment_id="exp1") == 1

    removed = store.drop_experiment("exp1")
    assert removed == 1  # 仅 1 条实验作用域边
    assert store.count_nodes(scope=GraphScope.GENERAL) == 4  # 通用 KG 不动
    assert store.count_edges(scope=GraphScope.EXPERIMENT) == 0
    assert {
        link.disease_key for link in store.protein_diseases("P1", experiment_id="exp1")
    } == {"D1"}


def test_experiment_edges_require_matching_query_context() -> None:
    store = InMemoryGraphStore()
    _seed_protein_disease(store)
    protein = NodeRef(NodeLabel.PROTEIN, "P1")

    assert store.neighbors(protein, EdgeType.ASSOCIATED_WITH) == []
    assert store.neighbors(
        protein, EdgeType.ASSOCIATED_WITH, experiment_id="other"
    ) == []
    assert len(
        store.neighbors(protein, EdgeType.ASSOCIATED_WITH, experiment_id="exp1")
    ) == 1


def test_replace_projection_removes_stale_experiment_relationships() -> None:
    store = InMemoryGraphStore()
    _seed_protein_disease(store)
    nodes = [
        GraphNode(NodeLabel.PROTEIN, "P1"),
        GraphNode(NodeLabel.GENE, "G1"),
        GraphNode(NodeLabel.DISEASE, "D1", properties={"name": "DiseaseOne"}),
    ]
    edges = [
        GraphEdge(
            EdgeType.ENCODED_BY,
            NodeRef(NodeLabel.PROTEIN, "P1"),
            NodeRef(NodeLabel.GENE, "G1"),
            key="P1|ENCODED_BY|G1",
        ),
        GraphEdge(
            EdgeType.ASSOCIATED_WITH,
            NodeRef(NodeLabel.GENE, "G1"),
            NodeRef(NodeLabel.DISEASE, "D1"),
            key="a1",
            properties={"evidence_level": "CONCLUSION"},
        ),
    ]

    result = store.replace_experiment_projection("exp1", nodes, edges)

    assert result["removed"] == 1
    assert store.count_edges(scope=GraphScope.EXPERIMENT, experiment_id="exp1") == 0
    assert {
        link.disease_key for link in store.protein_diseases("P1", experiment_id="exp1")
    } == {"D1"}


def test_replace_projection_rejects_missing_edge_endpoint() -> None:
    store = InMemoryGraphStore()
    with pytest.raises(ValueError, match="missing nodes"):
        store.replace_experiment_projection(
            "exp1",
            [GraphNode(NodeLabel.PROTEIN, "P1")],
            [
                GraphEdge(
                    EdgeType.ENCODED_BY,
                    NodeRef(NodeLabel.PROTEIN, "P1"),
                    NodeRef(NodeLabel.GENE, "G1"),
                    key="bad",
                )
            ],
        )


# ---------------- Neo4j 实现：Cypher 形状（不连库）----------------
class _RecordingNeo4j(Neo4jGraphStore):
    """跳过 driver，把 run 换成记录器；只验发出去的 Cypher 形状。"""

    def __init__(self) -> None:  # 故意不调 super().__init__（不连库、不导入 neo4j driver）
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._database = "neo4j"
        self._driver = _RecordingDriver(self.calls)

    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        self.calls.append((query, params))
        if "RETURN count(r) AS n" in query:
            return [{"n": len(params.get("rows", []))}]
        return []


class _RecordingResult:
    def __init__(self, count: int = 0) -> None:
        self.count = count

    def single(self) -> dict[str, int]:
        return {"n": self.count}

    def consume(self) -> None:
        return None


class _RecordingTransaction:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self.calls = calls

    def run(self, query: str, **params: Any) -> _RecordingResult:
        self.calls.append((query, params))
        return _RecordingResult(len(params.get("rows", [])))


class _RecordingSession:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self.calls = calls

    def __enter__(self) -> "_RecordingSession":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute_write(self, fn: Any) -> Any:
        return fn(_RecordingTransaction(self.calls))


class _RecordingDriver:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self.calls = calls

    def session(self, **_kwargs: Any) -> _RecordingSession:
        return _RecordingSession(self.calls)


def test_neo4j_initialize_schema_creates_constraint_per_label() -> None:
    store = _RecordingNeo4j()
    store.initialize_schema()
    joined = " ".join(q for q, _ in store.calls)
    for label in NodeLabel:
        assert f"FOR (n:{label.value}) REQUIRE n.key IS UNIQUE" in joined


def test_neo4j_upsert_groups_by_label_and_merges() -> None:
    store = _RecordingNeo4j()
    store.upsert_nodes(
        [GraphNode(NodeLabel.PROTEIN, "P1"), GraphNode(NodeLabel.GENE, "G1")]
    )
    queries = [q for q, _ in store.calls]
    assert any("MERGE (n:Protein {key: row.key})" in q for q in queries)
    assert any("MERGE (n:Gene {key: row.key})" in q for q in queries)


def test_neo4j_upsert_edges_match_endpoints_then_merge_rel() -> None:
    store = _RecordingNeo4j()
    store.upsert_edges(
        [
            GraphEdge(
                EdgeType.ENCODED_BY,
                NodeRef(NodeLabel.PROTEIN, "P1"),
                NodeRef(NodeLabel.GENE, "G1"),
                key="P1|ENCODED_BY|G1",
            )
        ]
    )
    q, params = store.calls[0]
    assert "MATCH (a:Protein {key: row.start_key})" in q
    assert "MATCH (b:Gene {key: row.end_key})" in q
    assert "MERGE (a)-[r:ENCODED_BY {key: row.key}]->(b)" in q
    assert params["rows"][0]["start_key"] == "P1"


def test_neo4j_drop_experiment_deletes_scoped_edges_and_nodes() -> None:
    store = _RecordingNeo4j()
    store.drop_experiment("exp1")
    queries = [q for q, _ in store.calls]
    assert any("DELETE r" in q and "EXPERIMENT" in q for q in queries)
    assert any("DETACH DELETE n" in q and "EXPERIMENT" in q for q in queries)
    assert all(p.get("exp") == "exp1" for _, p in store.calls)


def test_neo4j_replace_projection_uses_one_write_transaction() -> None:
    store = _RecordingNeo4j()
    nodes = [GraphNode(NodeLabel.PROTEIN, "P1"), GraphNode(NodeLabel.GENE, "G1")]
    edges = [
        GraphEdge(
            EdgeType.ENCODED_BY,
            NodeRef(NodeLabel.PROTEIN, "P1"),
            NodeRef(NodeLabel.GENE, "G1"),
            key="P1|ENCODED_BY|G1",
        )
    ]

    result = store.replace_experiment_projection("exp1", nodes, edges)

    assert result == {"removed": 0, "nodes": 2, "edges": 1}
    queries = [query for query, _ in store.calls]
    assert any("DELETE r" in query for query in queries)
    assert any("DETACH DELETE n" in query for query in queries)
    assert any("MERGE (a)-[r:ENCODED_BY" in query for query in queries)
