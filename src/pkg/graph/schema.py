"""图谱 schema 初始化:幂等地建约束 + 索引。"""
from __future__ import annotations
from typing import TYPE_CHECKING
from pkg.graph import cypher

if TYPE_CHECKING:
    from pkg.graph.store import GraphStore


def apply_graph_schema(store: "GraphStore") -> None:
    """连库后调一次即可;约束/索引都是 IF NOT EXISTS,重复调用安全。"""
    for stmt in cypher.CONSTRAINTS + cypher.INDEXES:
        store.run(stmt)