"""FASTA 精确子串查库(MVP)：肽序列是某蛋白序列的子串 = 命中。

de novo 的 I/L 同质量不可分，默认做 I→L 归一(两侧同时归一)，免得漏掉只差 I/L 的蛋白。
同源/容错匹配留给将来的 BLAST/DIAMOND 实现(同 ProteinDB 协议)。
"""
from __future__ import annotations

import os
from pathlib import Path

from pkg.protein_db.base import ProteinHit


def _parse_header(h: str) -> tuple[str, str]:
    """`sp|P12345|NAME Desc...` → ('P12345', 'Desc...')；非 UniProt 头退化取首 token。"""
    parts = h.split(None, 1)
    idtok = parts[0]
    desc = parts[1] if len(parts) > 1 else ""
    if idtok.count("|") >= 2:                       # sp|ACC|NAME / tr|ACC|NAME
        return idtok.split("|")[1], desc
    return idtok, desc


def parse_fasta(path: str | Path) -> dict[str, tuple[str, str]]:
    """解析 FASTA → ``{accession: (description, sequence)}``(多行序列拼接)。"""
    entries: dict[str, tuple[str, str]] = {}
    acc: str | None = None
    desc = ""
    seq_parts: list[str] = []
    with open(path, "rt", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if line.startswith(">"):
                if acc is not None:
                    entries[acc] = (desc, "".join(seq_parts))
                acc, desc = _parse_header(line[1:])
                seq_parts = []
            elif line.strip():
                seq_parts.append(line.strip())
        if acc is not None:
            entries[acc] = (desc, "".join(seq_parts))
    return entries


def _norm_il(s: str) -> str:
    return s.replace("I", "L")          # I/L 同质量不可分 → 归一到 L


class FastaProteinDB:
    """内存版精确子串查库。实现 ``ProteinDB`` 协议。"""

    def __init__(
        self,
        entries: dict[str, tuple[str, str]],
        *,
        name: str = "UniProt-FASTA",
        version: str = "unknown",
        il_equiv: bool = True,
    ) -> None:
        self.name = name
        self.version = version
        self.il_equiv = il_equiv
        self._desc = {acc: d for acc, (d, _s) in entries.items()}
        self._norm = _norm_il if il_equiv else (lambda x: x)
        # 预归一化序列，查询时只归一肽一侧
        self._index: list[tuple[str, str]] = [
            (acc, self._norm(seq)) for acc, (_d, seq) in entries.items()
        ]

    @classmethod
    def from_fasta(
        cls,
        path: str | Path,
        *,
        name: str = "UniProt-FASTA",
        version: str | None = None,
        il_equiv: bool = True,
    ) -> "FastaProteinDB":
        p = Path(path)
        return cls(parse_fasta(p), name=name, version=version or p.stem, il_equiv=il_equiv)

    def lookup(self, peptide_seq: str) -> list[ProteinHit]:
        if not peptide_seq:
            return []
        q = self._norm(peptide_seq)
        return [
            {"accession": acc, "description": self._desc[acc]}
            for acc, seq in self._index
            if q in seq
        ]


# ---------------- 进程内单例(对应 pkg.embedding.get_encoder)----------------
_db: FastaProteinDB | None = None


def get_protein_db() -> FastaProteinDB:
    """从环境变量加载 FASTA 蛋白库(MVP；日后并进 AppSettings)。

    ``PTAGENT_PROTEIN_DB_FASTA``  FASTA 路径(必填)
    ``PTAGENT_PROTEIN_DB_NAME``   库名(默认 UniProt-FASTA)
    ``PTAGENT_PROTEIN_DB_VERSION``库版本(默认取文件名 stem)
    """
    global _db
    if _db is None:
        path = os.environ.get("PTAGENT_PROTEIN_DB_FASTA")
        if not path:
            raise RuntimeError(
                "未配置蛋白库：设置环境变量 PTAGENT_PROTEIN_DB_FASTA 指向 .fasta 文件"
            )
        _db = FastaProteinDB.from_fasta(
            path,
            name=os.environ.get("PTAGENT_PROTEIN_DB_NAME", "UniProt-FASTA"),
            version=os.environ.get("PTAGENT_PROTEIN_DB_VERSION"),
        )
    return _db
