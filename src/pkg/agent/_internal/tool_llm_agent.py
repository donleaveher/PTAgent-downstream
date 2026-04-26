"""单节点：ToolGateway + LlmToolChatClient + RAG（与具体 MCP/OpenAI 解耦）。"""

from __future__ import annotations

import json
from typing import Any, Dict, Mapping

from jsonschema.exceptions import ValidationError

from ..contracts import AgentSpec, RAGRetriever, null_rag
from ..structured_output import (
    extract_json_from_assistant_text,
    structured_output_instruction_suffix,
    validate_against_json_schema,
)
from ..core import BaseAgent, RunContext
from ..ports import LlmToolChatClient, ToolGateway


def _compose_user_block(task: str, handoff: str) -> str:
    task = (task or "").strip()
    handoff = (handoff or "").strip()
    if task and handoff:
        return f"任务：\n{task}\n\n上轮 Agent 输出（handoff）：\n{handoff}"
    return task or handoff or ""


class ToolLlmAgent(BaseAgent):
    """
    通用「工具增强 LLM」节点：仅依赖 :class:`ToolGateway` 与 :class:`LlmToolChatClient`。
    """

    def __init__(
        self,
        spec: AgentSpec,
        *,
        tool_gateway: ToolGateway,
        llm: LlmToolChatClient,
        rag: RAGRetriever | None = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.2,
        max_tool_rounds: int = 8,
    ) -> None:
        super().__init__(name=spec.key, description=spec.description)
        self._spec = spec
        self._tools = tool_gateway
        self._llm = llm
        self._rag = rag if rag is not None else null_rag()
        self._model = model
        self._temperature = temperature
        self._max_tool_rounds = max_tool_rounds

    def run(self, context: RunContext, state: Mapping[str, Any]) -> Dict[str, Any]:
        data = dict(state.get("data") or {})
        task = (
            data.get("task")
            or data.get("user_message")
            or data.get("message")
            or ""
        )
        handoff = data.get("working_note") or data.get("handoff") or ""
        query_for_rag = str(task or handoff).strip()
        chunks = list(self._rag.retrieve(query_for_rag, k=4)) if query_for_rag else []
        user_block = _compose_user_block(str(task), str(handoff))

        tool_list = self._tools.list_tools()

        def execute_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
            return self._tools.call_tool(name, arguments)

        system_prompt = (self._spec.system_prompt or "").strip()
        schema_obj: dict[str, Any] | None = None
        if self._spec.interaction_mode == "structured":
            raw_meta = self._spec.meta.get("output_json_schema")
            if isinstance(raw_meta, dict):
                schema_obj = raw_meta
                system_prompt = (system_prompt + structured_output_instruction_suffix(schema_obj)).strip()

        text = self._llm.complete_with_tools(
            system_prompt=system_prompt,
            user_content=user_block,
            rag_chunks=chunks,
            tools=tool_list,
            execute_tool=execute_tool,
            model=self._model,
            temperature=self._temperature,
            max_tool_rounds=self._max_tool_rounds,
        )

        out_key = f"{self._spec.key}_output"
        structured_valid: bool | None = None
        structured_error: str | None = None
        final_text = text

        if self._spec.interaction_mode == "structured" and schema_obj is not None:
            try:
                parsed = extract_json_from_assistant_text(text)
                validate_against_json_schema(parsed, schema_obj)
                structured_valid = True
                final_text = json.dumps(parsed, ensure_ascii=False)
            except (ValueError, ValidationError) as exc:
                structured_valid = False
                structured_error = str(exc)
                final_text = text

        merged: Dict[str, Any] = {
            **data,
            out_key: final_text,
            "working_note": final_text,
            "last_agent": self._spec.key,
        }
        if structured_valid is not None:
            merged["structured_valid"] = structured_valid
        if structured_error:
            merged["structured_validation_error"] = structured_error
        return {"data": merged}
