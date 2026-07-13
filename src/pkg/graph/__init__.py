"""科学图谱底层存取包。

- **新版（L3，双节点知识图谱）**：通用 KG + 本次实验 KG。模型见 :mod:`pkg.graph.model`、
  端口/内存实现见 :mod:`pkg.graph.port`、Neo4j 实现见 :mod:`pkg.graph.neo4j_store`。
- **旧版（§13 待 deprecate，PSM/肽序列 KNN）**：:mod:`pkg.graph.store` /
  :mod:`pkg.graph.types` / :mod:`pkg.graph.cypher`，仅供旧上游路径与既有测试使用。
"""

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
from pkg.graph.identity import (
    CanonicalGeneIdentity,
    canonical_gene_identity,
    canonical_protein_key,
    canonical_relation_key,
    normalize_gene_symbol,
)
from pkg.graph.neo4j_store import Neo4jGraphStore, get_kg_store
from pkg.graph.port import GraphStore, InMemoryGraphStore

# --- 旧版（PSM/肽序列 KNN），保留供旧上游与既有测试使用 ---
from pkg.graph.store import get_graph_store
from pkg.graph.types import (
    EmbeddingRow,
    HypothesisRow,
    PepLookupRow,
    PepProtRow,
    ProtAnnotRow,
    TrunkRow,
)

__all__ = [
    # 新版 L3
    "CanonicalGeneIdentity",
    "Direction",
    "DiseaseLink",
    "EdgeType",
    "GraphEdge",
    "GraphNode",
    "GraphScope",
    "GraphStore",
    "InMemoryGraphStore",
    "Neo4jGraphStore",
    "NodeLabel",
    "NodeRef",
    "canonical_gene_identity",
    "canonical_protein_key",
    "canonical_relation_key",
    "get_kg_store",
    "normalize_gene_symbol",
    # 旧版
    "get_graph_store",
    "TrunkRow",
    "PepProtRow",
    "EmbeddingRow",
    "PepLookupRow",
    "ProtAnnotRow",
    "HypothesisRow",
]
