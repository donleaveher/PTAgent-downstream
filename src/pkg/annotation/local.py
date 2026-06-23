"""本地注释源(数据平面缓存层)：从 TSV/dict 按 accession 取 go/ec/interpro，离线、可测。

UniProt 全量一次性灌进 TSV(列 ``accession  go  ec  interpro``，多值用 ``;`` 分隔)，
enrich 从这里按 accession 取——"大库不进 Neo4j、只当缓存"的那一层就是它。
"""
from __future__ import annotations

import os
from pathlib import Path

from pkg.annotation.base import ProtAnnot


def _split(cell: str) -> list[str]:
    return [x for x in (c.strip() for c in cell.split(";")) if x]


def parse_annotation_tsv(path: str | Path) -> dict[str, ProtAnnot]:
    """TSV(首行表头含 accession/go/ec/interpro，多值 ``;`` 分隔)→ ``{acc: ProtAnnot}``。"""
    table: dict[str, ProtAnnot] = {}
    with open(path, "rt", encoding="utf-8") as fh:
        header = fh.readline().rstrip("\n").split("\t")
        idx = {h.strip(): i for i, h in enumerate(header)}

        def col(cols: list[str], key: str) -> list[str]:
            i = idx.get(key)
            return _split(cols[i]) if i is not None and i < len(cols) else []

        for raw in fh:
            if not raw.strip():
                continue
            cols = raw.rstrip("\n").split("\t")
            acc = cols[idx["accession"]].strip()
            if not acc:
                continue
            table[acc] = {
                "go": col(cols, "go"),
                "ec": col(cols, "ec"),
                "interpro": col(cols, "interpro"),
            }
    return table


class MappingAnnotationSource:
    """字典/TSV 支撑的注释源。实现 ``AnnotationSource`` 协议。"""

    def __init__(
        self,
        table: dict[str, ProtAnnot],
        *,
        name: str = "UniProt-local",
        version: str = "unknown",
    ) -> None:
        self._table = table
        self.name = name
        self.version = version

    @classmethod
    def from_tsv(
        cls,
        path: str | Path,
        *,
        name: str = "UniProt-local",
        version: str | None = None,
    ) -> "MappingAnnotationSource":
        p = Path(path)
        return cls(parse_annotation_tsv(p), name=name, version=version or p.stem)

    def fetch(self, accessions: list[str]) -> dict[str, ProtAnnot]:
        return {a: self._table[a] for a in accessions if a in self._table}


# ---------------- 进程内单例(对应 pkg.protein_db.get_protein_db)----------------
_src: MappingAnnotationSource | None = None


def get_annotation_source() -> MappingAnnotationSource:
    """从环境变量加载本地注释 TSV(MVP；日后并进 AppSettings / 接 UniProt 在线回填)。

    ``PTAGENT_ANNOT_TSV``      注释 TSV 路径(必填)
    ``PTAGENT_ANNOT_VERSION``  注释版本(默认取文件名 stem)
    """
    global _src
    if _src is None:
        tsv = os.environ.get("PTAGENT_ANNOT_TSV")
        if not tsv:
            raise RuntimeError(
                "未配置注释源：设置 PTAGENT_ANNOT_TSV 指向 accession/go/ec/interpro 的 TSV"
            )
        _src = MappingAnnotationSource.from_tsv(
            tsv, version=os.environ.get("PTAGENT_ANNOT_VERSION")
        )
    return _src
