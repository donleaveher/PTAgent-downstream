"""UniProt REST 在线注释源——占位骨架。

真实实现：UniProt ID-mapping / REST 批量按 accession 拉 GO / EC / InterPro 交叉引用，
解析成 ProtAnnot，并顺手落进本地 TSV 缓存(给 MappingAnnotationSource 复用)。
暂未接网——调用即报错，避免在没测过的网络代码上"假装能用"。
"""
from __future__ import annotations

from pkg.annotation.base import ProtAnnot


class UniProtAnnotationSource:
    """实现 ``AnnotationSource`` 协议；fetch 待接 UniProt REST。"""

    name = "UniProt-REST"

    def __init__(self, version: str = "unknown") -> None:
        self.version = version

    def fetch(self, accessions: list[str]) -> dict[str, ProtAnnot]:
        raise NotImplementedError(
            "UniProt 在线拉取未实现；当前用 MappingAnnotationSource(本地 TSV 缓存)。"
        )
