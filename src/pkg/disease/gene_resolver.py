"""accession → gene 解析。

结构近邻(M2)给的是 UniProt accession，而 CTD(M1)按 gene 查；M3 需要把近邻
accession 解析成 gene 才能借其疾病关联。`get_gene_resolver` 默认复用师兄的
UniProt MCP 工具（见 `pkg.annotation.uniprot_mcp.UniProtMCPGeneResolver`）；
测试用 `InMemoryGeneResolver` 注入。
"""

from __future__ import annotations

import re
from pathlib import Path
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

_AF_ACCESSION_RE = re.compile(r"AF-([A-Za-z0-9]+)-F\d+")


def _normalize_accession(value: str) -> str:
    """Normalize plain UniProt or AlphaFold model names to accession keys."""

    raw = value.strip()
    match = _AF_ACCESSION_RE.search(raw)
    if match:
        raw = match.group(1)
    return raw.upper()


def parse_static_gene_mapping(lines: Iterable[str]) -> dict[str, str]:
    """Parse a small accession→gene TSV/whitespace fixture.

    Expected columns: accession, gene_symbol. Blank lines and ``#`` comments are skipped.
    Extra columns are ignored to allow notes/provenance in local fixtures.
    """

    out: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t") if "\t" in line else line.split()
        if len(fields) < 2:
            continue
        accession = _normalize_accession(fields[0])
        gene = fields[1].strip()
        if accession and gene:
            out[accession] = gene
    return out


@runtime_checkable
class GeneResolver(Protocol):
    def resolve(self, accessions: list[str]) -> dict[str, str]:
        """accession → gene symbol；无法解析的可不出现在结果中。"""

        ...


class InMemoryGeneResolver:
    """字典支撑的解析器（测试 / MVP；真实解析见 `get_gene_resolver`）。"""

    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = dict(mapping)

    def resolve(self, accessions: list[str]) -> dict[str, str]:
        return {acc: self._mapping[acc] for acc in accessions if acc in self._mapping}


class StaticGeneResolver:
    """File-backed accession→gene resolver for local development without UniProt MCP."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self._mapping = {_normalize_accession(acc): gene for acc, gene in mapping.items()}

    @classmethod
    def from_file(cls, path: str | Path) -> "StaticGeneResolver":
        p = Path(path)
        with p.open("r", encoding="utf-8") as handle:
            return cls(parse_static_gene_mapping(handle))

    def resolve(self, accessions: list[str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for accession in accessions:
            gene = self._mapping.get(_normalize_accession(accession))
            if gene:
                out[accession] = gene
        return out


def get_gene_resolver() -> GeneResolver:
    """解析器工厂：生产默认 UniProt MCP；本地联调用 static TSV。"""

    from config import get_settings

    cfg = get_settings().annotation
    provider = cfg.gene_resolver_provider.strip().lower()
    if provider == "static":
        from config.paths import project_root

        path = Path(cfg.static_gene_mapping_file)
        if not path.is_absolute():
            path = project_root() / path
        if not path.exists():
            raise RuntimeError(
                f"static gene mapping file not found: {path}；"
                "设置 PTAGENT_ANNOTATION__STATIC_GENE_MAPPING_FILE 或切回 uniprot_mcp"
            )
        return StaticGeneResolver.from_file(path)
    if provider != "uniprot_mcp":
        raise ValueError(f"unsupported gene resolver provider: {cfg.gene_resolver_provider!r}")

    from config import get_mcp_settings
    from pkg.annotation.uniprot_mcp import UniProtMCPGeneResolver
    from pkg.mcp.client_pool import get_mcp_client

    client = get_mcp_client(get_mcp_settings().endpoint)
    return UniProtMCPGeneResolver(
        client,
        tool_name=cfg.uniprot_mcp_tool,
        accessions_argument=cfg.accessions_argument,
        batch_size=cfg.batch_size,
    )


__all__ = [
    "GeneResolver",
    "InMemoryGeneResolver",
    "StaticGeneResolver",
    "get_gene_resolver",
    "parse_static_gene_mapping",
]
