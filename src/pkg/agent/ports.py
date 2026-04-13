"""
与具体厂商解耦的边界：Agent 节点只依赖这些协议。

- :class:`ToolGateway`：工具发现与调用（可由 MCP、本地 stub、Mock 实现）
- :class:`LlmToolChatClient`：带 function-calling 的对话完成（可由 OpenAI、其它兼容实现或 Dry-run 实现）
- RAG 仍使用 ``contracts.RAGRetriever``，未实现时注入 ``null_rag()`` 即可
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, Sequence, runtime_checkable

from pkg.mcp.types import ToolInfo


@runtime_checkable
class ToolGateway(Protocol):
    """工具门面：列出可用工具并按名调用（与传输层 / MCP 解耦）。"""

    def list_tools(self) -> list[ToolInfo]:
        ...

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        ...


@runtime_checkable
class LlmToolChatClient(Protocol):
    """
    大模型 + 工具调用闭环（与 OpenAI SDK 解耦）。

    ``execute_tool`` 由上层注入，通常绑定到 :class:`ToolGateway`。
    """

    def complete_with_tools(
        self,
        *,
        system_prompt: str,
        user_content: str,
        rag_chunks: Sequence[str],
        tools: list[ToolInfo],
        execute_tool: Callable[[str, dict[str, Any]], dict[str, Any]],
        model: str,
        temperature: float,
        max_tool_rounds: int,
    ) -> str:
        ...
