from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence, runtime_checkable


def categories(*names: str) -> frozenset[str]:
    """构建 ``AgentSpec.mcp_categories`` 的便捷写法：``categories(\"basic\", \"spectral\")``。"""
    return frozenset(names)


@dataclass(frozen=True)
class AgentSpec:
    """
    描述一个可编排 Agent 的**纯配置**（无实现细节）。

    - ``key``：在工作流 / LangGraph 中的节点 ID，必须唯一。
    - ``mcp_categories``：允许调用的 MCP 工具类别；``None`` 表示不限制；
      空集合表示禁止任何 MCP 工具（仅 LLM + RAG 文本）。
    - ``mcp_tool_allowlist``：在类别过滤之后，再按工具名白名单收窄；``None`` 表示不按名过滤；
      空集合表示不允许任何工具调用。
    """

    key: str
    name: str = ""
    description: str = ""
    mcp_categories: frozenset[str] | None = None
    mcp_tool_allowlist: frozenset[str] | None = None
    system_prompt: str = ""
    #: 预留：对接独立 RAG 服务 / 向量库时的配置键（运行时由上层解析为 :class:`RAGRetriever`）
    rag_profile_id: str | None = None
    #: 本 Agent 使用的聊天模型名（OpenAI 兼容）
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.2
    meta: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        k = str(self.key).strip()
        if not k:
            raise ValueError("AgentSpec.key 不能为空")
        object.__setattr__(self, "key", k)
        if self.mcp_categories is not None and not isinstance(self.mcp_categories, frozenset):
            object.__setattr__(self, "mcp_categories", frozenset(self.mcp_categories))
        if self.mcp_tool_allowlist is not None and not isinstance(self.mcp_tool_allowlist, frozenset):
            object.__setattr__(self, "mcp_tool_allowlist", frozenset(self.mcp_tool_allowlist))

    @property
    def display_name(self) -> str:
        return (self.name or self.key).strip() or self.key


@runtime_checkable
class RAGRetriever(Protocol):
    """RAG 最小协议：给定查询返回若干文本片段（由具体项目实现向量库 / 检索）。"""

    def retrieve(self, query: str, *, k: int = 4) -> Sequence[str]:
        ...


class _NullRAG:
    def retrieve(self, query: str, *, k: int = 4) -> Sequence[str]:
        return ()


def null_rag() -> RAGRetriever:
    """无检索占位实现，便于默认关闭 RAG。"""
    return _NullRAG()
