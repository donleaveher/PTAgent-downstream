"""下游蛋白基础注释配置。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnnotationSettings(BaseModel):
    """UniProt MCP 注释工具的调用约定。"""

    uniprot_mcp_tool: str = Field(
        "get_protein_annotations",
        min_length=1,
        description="师兄提供的 UniProt 蛋白注释 MCP 工具名。",
    )
    accessions_argument: str = Field(
        "accessions",
        min_length=1,
        description="MCP 工具接收 accession 批次的参数名。",
    )
    batch_size: int = Field(100, ge=1, le=1000, description="单次 MCP 调用的 accession 数量。")
    source_version: str = Field(
        "MCP-current",
        min_length=1,
        description="工具未返回数据库版本时使用的 provenance 版本。",
    )


__all__ = ["AnnotationSettings"]
