"""统一执行路径：编译 LLM 客户端 + 在图上 invoke。"""

from __future__ import annotations

from typing import Any

from ._internal.graph import build_linear_agent_graph
from ._internal.openai_llm_tool_client import OpenAiLlmToolClient
from .core import RunContext
from .ports import LlmToolChatClient


def compile_llm_client() -> LlmToolChatClient:
    """返回 OpenAI 兼容的 LLM 工具客户端（真实调用）。"""
    from pkg.llm.openai_runtime import build_openai_client

    return OpenAiLlmToolClient(build_openai_client())


def run_invocation(
    graph: Any,
    *,
    task: str,
    run_id: str = "ptagent-run",
    extra_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """对已编译 LangGraph 执行一次 invoke。"""
    ctx = RunContext(run_id=run_id)
    data: dict[str, Any] = {"task": task}
    if extra_data:
        data.update({str(k): v for k, v in extra_data.items()})
    state: dict[str, Any] = {
        "context": ctx,
        "data": data,
        "logs": [],
    }
    return graph.invoke(state)


def run_single_agent_graph(
    spec: Any,
    *,
    task: str,
    endpoint: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    run_id: str = "single-agent",
) -> dict[str, Any]:
    """单 Agent：线性单节点图 + invoke。"""
    from .contracts import AgentSpec, null_rag
    from .team import create_llm_mcp_agent

    if not isinstance(spec, AgentSpec):
        raise TypeError("spec 必须为 AgentSpec")
    llm = compile_llm_client()
    m = model if model is not None else spec.llm_model
    temp = temperature if temperature is not None else spec.llm_temperature
    agent = create_llm_mcp_agent(
        spec, endpoint=endpoint, rag=null_rag(), llm=llm, model=m, temperature=temp
    )
    graph = build_linear_agent_graph([agent])
    result = run_invocation(graph, task=task, run_id=run_id)
    return {"result": result}
