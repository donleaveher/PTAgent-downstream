"""accession → gene 解析。

结构近邻(M2)给的是 UniProt accession，而 CTD(M1)按 gene 查；M3 需要把近邻
accession 解析成 gene 才能借其疾病关联。`get_gene_resolver` 默认复用师兄的
UniProt MCP 工具（见 `pkg.annotation.uniprot_mcp.UniProtMCPGeneResolver`）；
测试用 `InMemoryGeneResolver` 注入。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


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


def get_gene_resolver() -> GeneResolver:
    """默认解析器：复用师兄的 UniProt MCP 工具（与蛋白注释同工具/配置）。"""

    from config import get_mcp_settings, get_settings
    from pkg.annotation.uniprot_mcp import UniProtMCPGeneResolver
    from pkg.mcp.client_pool import get_mcp_client

    cfg = get_settings().annotation
    client = get_mcp_client(get_mcp_settings().endpoint)
    return UniProtMCPGeneResolver(
        client,
        tool_name=cfg.uniprot_mcp_tool,
        accessions_argument=cfg.accessions_argument,
        batch_size=cfg.batch_size,
    )


__all__ = ["GeneResolver", "InMemoryGeneResolver", "get_gene_resolver"]
