"""注释传递的纯数据类型。"""
from __future__ import annotations

from typing import TypedDict

# 一个蛋白的注释(按类型)：{'go': [...], 'ec': [...], 'interpro': [...]}
ProtFeatures = dict[str, list[str]]


class Neighbor(TypedDict, total=False):
    """一个相似邻居 = 邻居肽 id + 相似度 + 其母蛋白注释(按 accession 分组，保出处)。

    一条肽可能映射到多个蛋白(共享肽)，所以属性按 accession 分开存，不在传递时就 union 压平。
    """
    id: str
    score: float
    proteins: dict[str, ProtFeatures]      # {accession: {go, ec, interpro}}


class Support(TypedDict):
    """一条预测的一个支持来源：哪个邻居、经由它的哪些蛋白带了这个属性。"""
    neighbor: str
    via: list[str]                         # accession 列表


class Prediction(TypedDict):
    """一条预测属性 + 可解释的两个因子(相似度 × 共识度)。"""
    attr_type: str          # 'go' / 'ec' / 'interpro'
    predicted: str          # 预测到的属性值
    support: list[Support]  # 支持来源(邻居 + 经由哪些蛋白)
    sim: float              # 相似度：支持邻居的平均相似度
    consensus: float        # 共识度：支持邻居占全部邻居比例
    confidence: float       # = sim × consensus
