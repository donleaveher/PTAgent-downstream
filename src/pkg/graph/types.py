from __future__ import annotations
from typing import Any, TypedDict

class TrunkRow(TypedDict, total = False):
    """主干一行 = 一条 PSM 拍平后的全部字段(喂给 MERGE_TRUNK 的 $rows)。"""
    # ── 来自谱图文件 ──
    spectrum_id: str
    precursor_mz: float | None
    charge: int | None
    retention_time: float | None
    scan_index: int
    spectra_object_id: str          # 溯源:谱图文件 object_id
    # ── 来自结果文件 ──
    psm_id: str
    score: float | None
    q_value: float | None
    aa_scores: list[float]
    search_engine: str
    is_decoy: bool
    result_object_id: str           # 溯源:结果文件 object_id
    # ── 肽段 ──
    peptidoform: str                # 节点身份(带修饰)
    stripped_sequence: str
    length: int
    # ── 上下文 ──
    sample_id: str
    sample_name: str
    condition: str
    run_id: str                     # 溯源:本次运行

class PepProtRow(TypedDict, total=False):
    """蛋白层一行 = 肽段→蛋白的一条归属边(喂给 MERGE_PEP_PROT 的 $pep_prot)。"""
    peptidoform: str
    accession: str
    description: str

class EmbeddingRow(TypedDict, total=False):
    """一条肽的序列向量(喂给 SET_EMBEDDINGS 的 $rows)。"""
    peptidoform: str        # 写到哪个 Peptide 节点
    embedding: list[float]  # 该肽裸序列的定长向量

class PepLookupRow(TypedDict, total=False):
    """阶段3 查库结果一行(命中与否都记) → 写 Peptide 的 novelty 标注。

    "搜了没命中"显式记成 db_hit=false,区别于"还没搜"(节点上根本没这属性);
    novel 是相对"搜了哪个库的哪个版本",所以连 db_name/db_version 一起记。
    """
    peptidoform: str    # 写到哪个 Peptide 节点
    db_hit: bool        # 是否找到含此肽的蛋白(False = novel)
    db_name: str        # 搜了哪个库,如 'UniProt-SwissProt'
    db_version: str     # 库版本,如 '2026_01'

class ProtAnnotRow(TypedDict, total=False):
    """阶段3.5 富集一行 = 一个蛋白从 UniProt 提取的注释属性(喂给 MERGE_PROT_ANNOT)。"""
    accession: str          # 写到哪个 Protein 节点
    go: list[str]           # GO term id 集合
    ec: list[str]           # EC number 集合
    interpro: list[str]     # InterPro id 集合
    source: str             # 注释来源,默认 'UniProt'
    version: str            # 注释版本(溯源),如 '2026_01'

class HypothesisRow(TypedDict, total=False):
    """阶段6 假说一条 = 对某条肽预测的一个属性 + 证据(注释传递的产物)。

    不入图(瞬时使用,喂 deep-search/报告);这里只是阶段间传递的结构。
    """
    peptidoform: str            # 主语:被预测的肽
    attr_type: str              # 属性类型: 'go'/'ec'/'interpro'/...
    predicted: str              # 预测到的具体属性值(如某 GO id)
    support: list[dict[str, Any]]  # 证据:[{neighbor, via:[accession,...]}] 邻居 + 经由哪些蛋白
    confidence: float           # 置信度 = 相似度 × 共识度