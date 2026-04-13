"""OpenAI Chat Completions + tools 的具体实现（仅被适配层使用）。"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Sequence

from openai import OpenAI

from pkg.mcp.types import ToolInfo

from ..ports import LlmToolChatClient


def _safe_parameters(schema: Dict[str, Any]) -> Dict[str, Any]:
    if schema and isinstance(schema, dict):
        return schema
    return {"type": "object", "properties": {}, "additionalProperties": True}


def _tools_to_openai_format(tools: List[ToolInfo]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for t in tools:
        out.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": (t.description or "")[:4096],
                    "parameters": _safe_parameters(t.input_schema),
                },
            }
        )
    return out


def _build_system_prompt(base: str, rag_chunks: Sequence[str]) -> str:
    parts: List[str] = []
    if base.strip():
        parts.append(base.strip())
    if rag_chunks:
        joined = "\n---\n".join(c.strip() for c in rag_chunks if c and str(c).strip())
        if joined:
            parts.append("以下为检索到的参考片段（RAG），请结合任务使用：\n" + joined)
    return "\n\n".join(parts) if parts else "你是一个协助分析任务的助手。"


def _tool_result_content(result: Dict[str, Any]) -> str:
    try:
        return json.dumps(result, ensure_ascii=False)
    except TypeError:
        return json.dumps({"_repr": repr(result)}, ensure_ascii=False)


class OpenAiLlmToolClient(LlmToolChatClient):
    """基于 OpenAI SDK 的 :class:`~pkg.agent.ports.LlmToolChatClient` 实现。"""

    def __init__(self, client: OpenAI) -> None:
        self._client = client

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
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": _build_system_prompt(system_prompt, rag_chunks)},
            {"role": "user", "content": user_content},
        ]
        oai_tools = _tools_to_openai_format(tools)

        for _ in range(max_tool_rounds):
            kwargs: Dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
            if oai_tools:
                kwargs["tools"] = oai_tools

            resp = self._client.chat.completions.create(**kwargs)
            msg = resp.choices[0].message

            assistant: Dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                assistant["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments or "{}",
                        },
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(assistant)

            if not msg.tool_calls:
                return msg.content or ""

            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    raw_args = tc.function.arguments or "{}"
                    args = json.loads(raw_args) if raw_args.strip() else {}
                except json.JSONDecodeError:
                    args = {}
                if not isinstance(args, dict):
                    args = {}
                try:
                    result = execute_tool(name, args)
                except Exception as exc:  # noqa: BLE001
                    result = {"error": str(exc), "tool": name}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": _tool_result_content(result),
                    }
                )

        return ""
