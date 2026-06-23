"""蛋白注释源的抽象：给一批 accession，返回 go/ec/interpro。

本地 TSV 缓存(MappingAnnotationSource)是离线可测的主路径；UniProt 在线(UniProtAnnotationSource)
负责把全量灌进缓存。上层(enrich_annot)只依赖这个协议，换源不改编排。
"""
from __future__ import annotations

from typing import Protocol, TypedDict, runtime_checkable


class ProtAnnot(TypedDict, total=False):
    """一个蛋白的注释属性(集合)。"""
    go: list[str]
    ec: list[str]
    interpro: list[str]


@runtime_checkable
class AnnotationSource(Protocol):
    """accession → 注释 查询接口。name/version 写进 Protein 的 provenance。"""

    name: str
    version: str

    def fetch(self, accessions: list[str]) -> dict[str, "ProtAnnot"]:
        """批量取注释；返回 ``{accession: {go, ec, interpro}}``，查不到的不出现在结果里。"""
        ...
