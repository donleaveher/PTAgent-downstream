"""蛋白库查询的抽象：给一条肽序列，返回"含此肽的蛋白"。

精确子串(FastaProteinDB)是 MVP 实现；BLAST/DIAMOND 同源那一路日后实现
同一个 ``ProteinDB`` 协议接进来即可，上层(db_assign)无需改动。
"""
from __future__ import annotations

from typing import Protocol, TypedDict, runtime_checkable


class ProteinHit(TypedDict):
    """命中一条 = 含此肽的一个蛋白。"""
    accession: str
    description: str


@runtime_checkable
class ProteinDB(Protocol):
    """肽 → 蛋白 查询接口。实现需提供库名/版本(写进 novelty 标注的 provenance)。"""

    name: str
    version: str

    def lookup(self, peptide_seq: str) -> list[ProteinHit]:
        """返回序列里含此肽的蛋白；空列表 = 没命中(novel)。"""
        ...
