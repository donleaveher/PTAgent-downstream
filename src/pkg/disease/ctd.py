"""CTD genes-diseases 文件 parser 与文件数据源。

只提取**直接证据**（DirectEvidence 非空，如 marker/mechanism、therapeutic）作为结论级；
仅由化学物推断（InferenceChemicalName）得到的间接关联被排除——这些不是直接事实。
对标 `pkg.annotation.uniprot_mcp`（归一外部源为标准事实）。
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Iterator
from pathlib import Path

from pkg.disease.types import GeneDiseaseFact

# CTD genes-diseases CSV 列顺序（文件无表头，列名见 CTD 文档注释块）。
_COL = {
    "gene_symbol": 0,
    "gene_id": 1,
    "disease_name": 2,
    "disease_id": 3,
    "direct_evidence": 4,
    "inference_chemical": 5,
    "inference_score": 6,
    "omim_ids": 7,
    "pubmed_ids": 8,
}
_DEFAULT_DIRECT_TYPES: tuple[str, ...] = ("marker/mechanism", "therapeutic")


def _normalize_gene(symbol: str) -> str:
    return symbol.strip().upper()


def _split_multi(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split("|") if part.strip())


def iter_direct_evidence_rows(
    lines: Iterable[str],
    *,
    direct_evidence_types: tuple[str, ...] = _DEFAULT_DIRECT_TYPES,
) -> Iterator[tuple[list[str], list[str]]]:
    """逐行 yield 通过"直接证据"过滤的 ``(CSV 行, 命中的证据类型)``。

    parser 与预处理脚本共用此函数，单源维护列位置与过滤规则、避免漂移。
    跳过注释行；丢弃 DirectEvidence 为空（纯化学物推断的间接关联）或类型不在允许列表的行。
    """

    allow = {t.strip().lower() for t in direct_evidence_types}
    rows = csv.reader(line for line in lines if line and not line.lstrip().startswith("#"))
    for row in rows:
        if len(row) <= _COL["direct_evidence"]:
            continue
        direct = row[_COL["direct_evidence"]].strip()
        if not direct:
            continue  # 间接（化学物推断）→ 不作结论
        kept = [token.strip() for token in direct.split("|") if token.strip().lower() in allow]
        if not kept:
            continue
        yield row, kept


def parse_ctd_genes_diseases(
    lines: Iterable[str],
    *,
    direct_evidence_types: tuple[str, ...] = _DEFAULT_DIRECT_TYPES,
    version: str = "CTD-unknown",
) -> dict[str, list[GeneDiseaseFact]]:
    """解析 CTD genes-diseases CSV，仅保留直接证据，按 UPPER(gene) 归并。"""

    out: dict[str, list[GeneDiseaseFact]] = {}
    for row, kept in iter_direct_evidence_rows(
        lines, direct_evidence_types=direct_evidence_types
    ):
        gene = row[_COL["gene_symbol"]].strip()
        disease_id = row[_COL["disease_id"]].strip()
        if not gene or not disease_id:
            continue
        gene_id = row[_COL["gene_id"]].strip() if len(row) > _COL["gene_id"] else ""
        pubmed = (
            _split_multi(row[_COL["pubmed_ids"]]) if len(row) > _COL["pubmed_ids"] else ()
        )
        fact = GeneDiseaseFact(
            gene=gene,
            disease_id=disease_id,
            disease_name=row[_COL["disease_name"]].strip(),
            evidence_type="|".join(kept),
            relation_id=f"{gene_id or gene}|{disease_id}",
            pubmed_ids=pubmed,
            provenance={"source_db": "CTD", "db_version": version, "gene_id": gene_id},
        )
        out.setdefault(_normalize_gene(gene), []).append(fact)
    return out


class CTDFileDiseaseSource:
    """从本地 CTD genes-diseases 文件提供直接证据级 基因-疾病 关联。"""

    name = "CTD"

    def __init__(
        self,
        index: dict[str, list[GeneDiseaseFact]],
        *,
        version: str = "CTD-unknown",
    ) -> None:
        self._index = index
        self.version = version

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        direct_evidence_types: tuple[str, ...] = _DEFAULT_DIRECT_TYPES,
        version: str = "CTD-unknown",
    ) -> "CTDFileDiseaseSource":
        with Path(path).open("r", encoding="utf-8") as handle:
            index = parse_ctd_genes_diseases(
                handle, direct_evidence_types=direct_evidence_types, version=version
            )
        return cls(index, version=version)

    def fetch(self, genes: list[str]) -> dict[str, list[GeneDiseaseFact]]:
        out: dict[str, list[GeneDiseaseFact]] = {}
        for gene in genes:
            facts = self._index.get(_normalize_gene(gene))
            if facts:
                out[gene] = facts
        return out


def get_disease_source() -> CTDFileDiseaseSource:
    from config import get_settings
    from config.paths import project_root

    cfg = get_settings().ctd
    path = Path(cfg.data_file)
    if not path.is_absolute():
        path = project_root() / path
    return CTDFileDiseaseSource.from_file(
        path,
        direct_evidence_types=tuple(cfg.direct_evidence_types),
        version=cfg.version,
    )


__all__ = [
    "CTDFileDiseaseSource",
    "get_disease_source",
    "iter_direct_evidence_rows",
    "parse_ctd_genes_diseases",
]
