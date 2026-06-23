"""Neo4j driver 封装:批量 MERGE、跑 GDS 推断、查询。镜像 data_plane.store。"""
from __future__ import annotations
from typing import Any
from neo4j import GraphDatabase
from pkg.graph import cypher
from pkg.graph.schema import apply_graph_schema
from pkg.graph.types import (
    TrunkRow, PepProtRow, EmbeddingRow, PepLookupRow, ProtAnnotRow,
)


class GraphStore:
    def __init__(self, uri: str, user: str, password: str) -> None:
        # neo4j driver 本身线程安全,session 很轻量 → 不像 sqlite 那样需要自带锁
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self._driver.close()

    def apply_schema(self) -> None:
        apply_graph_schema(self)

    # ---- 底层执行 ----
    def run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        with self._driver.session() as s:
            return s.run(query, **params).data()

    # ---- 写入(分批,避免单条 UNWIND 过大)----
    def merge_trunk(self, rows: list[TrunkRow], batch: int = 1000) -> int:
        for i in range(0, len(rows), batch):
            self.run(cypher.MERGE_TRUNK, rows=rows[i:i + batch])
        return len(rows)

    def merge_pep_prot(self, pep_prot: list[PepProtRow], batch: int = 1000) -> int:
        for i in range(0, len(pep_prot), batch):
            self.run(cypher.MERGE_PEP_PROT, pep_prot=pep_prot[i:i + batch])
        return len(pep_prot)

    # ---- 推断(⑤⑥,按顺序跑)----
    def run_inference(self) -> None:
        for stmt in cypher.INFERENCE_STEPS:
            self.run(stmt)

    # ---- ⑧ 序列 embedding + KNN 相似 ----
    def list_unembedded(self) -> list[dict[str, Any]]:
        """返回还没 embedding 的肽：[{peptidoform, seq}]。"""
        return self.run(cypher.Q_UNEMBEDDED)

    def write_embeddings(self, rows: list[EmbeddingRow], batch: int = 500) -> int:
        for i in range(0, len(rows), batch):
            self.run(cypher.SET_EMBEDDINGS, rows=rows[i:i + batch])
        return len(rows)

    def run_knn(self, k: int = 5, cutoff: float = 0.8) -> None:
        """按 embedding 跑 gds.knn，写出 SIMILAR_TO 相似边（需 GDS 插件）。"""
        for stmt in cypher.KNN_STEPS:
            self.run(stmt, k=k, cutoff=cutoff)

    def similar_peptides(self, peptidoform: str) -> list[dict[str, Any]]:
        """查一条肽的序列近邻（给假说阶段用）。"""
        return self.run(cypher.Q_SIMILAR_PEPTIDES, peptidoform=peptidoform)

    # ---- ⑨ 查库 novelty 标注(阶段3)----
    def list_unsearched_peptides(self) -> list[dict[str, Any]]:
        """返回还没查库的肽(db_searched 未标)：[{peptidoform, seq}]。"""
        return self.run(cypher.Q_UNSEARCHED)

    def write_lookup(self, rows: list[PepLookupRow], batch: int = 1000) -> int:
        """把查库结果(命中与否)写成 Peptide 的 novelty 标注。"""
        for i in range(0, len(rows), batch):
            self.run(cypher.MERGE_PEP_LOOKUP, rows=rows[i:i + batch])
        return len(rows)

    def list_novel_peptides(self) -> list[dict[str, Any]]:
        """返回 novel 肽(查库没命中)：[{peptidoform, seq}]。"""
        return self.run(cypher.Q_NOVEL_PEPTIDES)

    # ---- ⑩ 蛋白注释富集(阶段3.5)----
    def list_unannotated_proteins(self) -> list[dict[str, Any]]:
        """返回还没富集注释的蛋白：[{accession}]。"""
        return self.run(cypher.Q_UNANNOTATED)

    def write_annotations(self, rows: list[ProtAnnotRow], batch: int = 500) -> int:
        """把 UniProt 注释写成 Protein 节点属性(go/ec/interpro + provenance)。"""
        for i in range(0, len(rows), batch):
            self.run(cypher.MERGE_PROT_ANNOT, rows=rows[i:i + batch])
        return len(rows)

    # ---- ⑪ 混合检索(阶段5)----
    def peptide_corpus(self) -> list[dict[str, Any]]:
        """读肽语料：[{peptidoform, seq, attrs}]（attrs = 所属蛋白注释并集）。"""
        return self.run(cypher.Q_PEPTIDE_CORPUS)

    def write_similarity(self, pairs: list[dict[str, Any]], batch: int = 1000) -> int:
        """把混合检索 top-k 写成 SIMILAR_TO 边（method='hybrid'）。"""
        for i in range(0, len(pairs), batch):
            self.run(cypher.MERGE_SIMILAR, pairs=pairs[i:i + batch])
        return len(pairs)

    # ---- ⑫ 假说：邻居 + 母蛋白注释(阶段6)----
    def neighbor_annotations(self, peptidoform: str) -> list[dict[str, Any]]:
        """取一条肽的相似邻居及其母蛋白注释：[{id, score, go, ec, interpro}]。"""
        return self.run(cypher.Q_NEIGHBOR_ANNOTS, peptidoform=peptidoform)

    # ---- 常用查询 ----
    def peptide_support(self, max_q: float = 0.01) -> list[dict[str, Any]]:
        return self.run(cypher.Q_PEPTIDE_SUPPORT, max_q=max_q)


# ---------------- 进程内单例(对应 data_plane 的 get_data_plane_store)----------------
_store: GraphStore | None = None


def get_graph_store() -> GraphStore:
    global _store
    if _store is None:
        from config.graph_settings import get_graph_settings   # 待新增的配置
        s = get_graph_settings()
        _store = GraphStore(s.uri, s.user, s.password)
        _store.apply_schema()        # 首次连库时建好约束/索引
    return _store