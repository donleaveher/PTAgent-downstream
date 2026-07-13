"""Deep-search 文献 MCP 的调用约定与可靠性配置。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DeepSearchSettings(BaseModel):
    """生产文献检索 MCP 的配置；环境变量前缀为 PTAGENT_DEEP_SEARCH__。"""

    provider: Literal["pubmed", "generic_mcp"] = Field(
        "pubmed",
        description="文献召回源：本项目自托管 PubMed MCP 或兼容的通用 MCP 工具。",
    )
    literature_mcp_endpoint: str = Field(
        "http://127.0.0.1:3010/mcp",
        min_length=1,
        description="下游文献 MCP 的 Streamable HTTP 地址；与上游数据处理无关。",
    )
    mcp_tool: str = Field(
        "pubmed_search_articles",
        min_length=1,
        description="文献检索 MCP 工具名；PubMed 默认 pubmed_search_articles。",
    )
    query_argument: str = Field(
        "query",
        min_length=1,
        description="MCP 工具接收规范化检索语句的参数名。",
    )
    limit_argument: str = Field(
        "maxResults",
        min_length=1,
        description="MCP 工具接收结果上限的参数名。",
    )
    fetch_mcp_tool: str = Field(
        "pubmed_fetch_articles",
        min_length=1,
        description="PubMed 详情工具名；用于将 PMID 扩充为标题、摘要和 MeSH。",
    )
    max_results: int = Field(5, ge=1, le=100, description="单条假说最多检索的文献数。")
    candidate_fallback_max_queries: int = Field(
        3,
        ge=0,
        le=10,
        description="原始基因零命中时，最多尝试多少个近邻 candidate gene 的补充 PubMed 查询。",
    )
    timeout_seconds: float = Field(
        20.0,
        gt=0,
        le=300,
        description="单次 MCP 工具调用的本地等待上限。",
    )
    max_attempts: int = Field(2, ge=1, le=5, description="调用失败时的最大尝试次数。")
    retry_backoff_seconds: float = Field(
        1.0,
        ge=0,
        le=60,
        description="重试基础退避秒数；第 n 次重试等待 n 倍该值。",
    )
    source_version: str = Field(
        "pubmed-mcp-v2.9.8",
        min_length=1,
        description="工具未返回版本时写入证据 provenance 的版本。",
    )
    default_stance: str = Field(
        "neutral",
        pattern="^(support|refute|neutral)$",
        description="MCP 结果缺少明确立场时的保守默认值。",
    )
    max_snippet_chars: int = Field(
        1000,
        ge=0,
        le=10000,
        description="单条证据保存的摘要片段最大字符数。",
    )


__all__ = ["DeepSearchSettings"]
