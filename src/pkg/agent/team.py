from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Sequence

from config import get_mcp_settings

from pkg.llm.openai_runtime import build_openai_client
from pkg.mcp.client_pool import get_mcp_client

from ._internal.graph import build_linear_agent_graph
from ._internal.mcp_scope import McpToolScope
from ._internal.openai_llm_tool_client import OpenAiLlmToolClient
from ._internal.team_graph import graph_to_next_map, is_industrial_graph, validate_team_graph
from ._internal.tool_llm_agent import ToolLlmAgent
from ._internal.workflow_dynamic_agents import EndWorkflowAgent, McpToolWorkflowAgent, StartWorkflowAgent
from .contracts import AgentSpec, RAGRetriever
from .core import BaseAgent
from .ports import LlmToolChatClient, ToolGateway
from .registry import TeamSpec
from .workflow import WorkflowConfig, WorkflowNodeConfig, build_workflow_graph


def create_tool_llm_agent(
    spec: AgentSpec,
    *,
    tool_gateway: ToolGateway,
    llm: LlmToolChatClient,
    rag: RAGRetriever | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tool_rounds: int = 8,
) -> BaseAgent:
    """
    由协议实现组装 :class:`BaseAgent`（推荐用于单元测试或自定义 LLM/MCP 适配器）。
    """
    m = model if model is not None else spec.llm_model
    temp = temperature if temperature is not None else spec.llm_temperature
    return ToolLlmAgent(
        spec,
        tool_gateway=tool_gateway,
        llm=llm,
        rag=rag,
        model=m,
        temperature=temp,
        max_tool_rounds=max_tool_rounds,
    )


def create_llm_mcp_agent(
    spec: AgentSpec,
    *,
    endpoint: str | None = None,
    rag: RAGRetriever | None = None,
    llm: LlmToolChatClient | None = None,
    model: str | None = None,
    temperature: float | None = None,
    max_tool_rounds: int = 8,
) -> BaseAgent:
    """
    便捷工厂：默认使用 Broker MCP + OpenAI 兼容接口。

    传入 ``llm`` 可替换为其它 :class:`~pkg.agent.ports.LlmToolChatClient` 实现。
    """
    ep = endpoint or get_mcp_settings().endpoint
    client = get_mcp_client(ep)
    scope = McpToolScope(client, spec)
    chat = llm if llm is not None else OpenAiLlmToolClient(build_openai_client())
    m = model if model is not None else spec.llm_model
    temp = temperature if temperature is not None else spec.llm_temperature
    return ToolLlmAgent(
        spec,
        tool_gateway=scope,
        llm=chat,
        rag=rag,
        model=m,
        temperature=temp,
        max_tool_rounds=max_tool_rounds,
    )


def build_linear_mcp_team(
    agents: Sequence[AgentSpec],
    *,
    endpoint: str | None = None,
    rag_by_agent: Mapping[str, RAGRetriever] | None = None,
    llm: LlmToolChatClient | None = None,
    model: str | None = None,
    temperature: float | None = None,
):
    """
    按给定顺序构建**线性**多 Agent 图（前一个节点的 ``working_note`` 作为下一节点 handoff）。
    """
    if not agents:
        raise ValueError("至少需要一个 AgentSpec")
    rag_by_agent = rag_by_agent or {}
    instances: list[BaseAgent] = []
    for spec in agents:
        rag = rag_by_agent.get(spec.key)
        instances.append(
            create_llm_mcp_agent(
                spec,
                endpoint=endpoint,
                rag=rag,
                llm=llm,
                model=model,
                temperature=temperature,
            )
        )
    return build_linear_agent_graph(instances)


def build_mcp_workflow_graph(
    agents: Mapping[str, AgentSpec],
    *,
    entry_key: str,
    next_map: Mapping[str, Sequence[str]],
    endpoint: str | None = None,
    rag_by_agent: Mapping[str, RAGRetriever] | None = None,
    llm: LlmToolChatClient | None = None,
    model: str | None = None,
    temperature: float | None = None,
):
    """
    按显式邻接表 ``next_map`` 构建工作流。

    ``agents`` 的 key 必须与 :class:`AgentSpec` 的 ``key`` 一致。
    """
    rag_by_agent = rag_by_agent or {}
    nodes: list[WorkflowNodeConfig] = []
    for key, spec in agents.items():
        if spec.key != key:
            raise ValueError(f"AgentSpec.key ({spec.key!r}) 必须与映射键 ({key!r}) 相同")
        nxt = list(next_map.get(key) or [])
        agent = create_llm_mcp_agent(
            spec,
            endpoint=endpoint,
            rag=rag_by_agent.get(key),
            llm=llm,
            model=model,
            temperature=temperature,
        )
        nodes.append(
            WorkflowNodeConfig(
                key=key,
                agent=agent,
                next_keys=nxt if nxt else None,
            )
        )
    cfg = WorkflowConfig(nodes=nodes, entry_key=entry_key)
    return build_workflow_graph(cfg)


def _compile_industrial_team_graph(
    g: dict[str, Any],
    *,
    agent_specs_by_key: Mapping[str, AgentSpec],
    endpoint: str | None,
    rag_by_agent: Mapping[str, RAGRetriever] | None,
    llm: LlmToolChatClient | None,
    model: str | None,
    temperature: float | None,
):
    ep = endpoint or get_mcp_settings().endpoint
    client = get_mcp_client(ep)
    call_tool = client.call_tool
    entry = str(g["entry"]).strip()
    next_map = graph_to_next_map(g)
    input_keys = list(g.get("inputKeys") or ["task"])
    graph_output_keys = list(g.get("outputKeys") or ["working_note"])
    rag_by_agent = rag_by_agent or {}
    node_cfgs: list[WorkflowNodeConfig] = []
    raw_nodes = [n for n in (g.get("nodes") or []) if isinstance(n, dict)]
    for n in raw_nodes:
        wid = str(n.get("id") or "").strip()
        kind = str(n.get("kind") or "").strip()
        nxt = next_map.get(wid) or []
        ag: BaseAgent
        if kind == "start":
            ag = StartWorkflowAgent(wid, input_keys=input_keys)
        elif kind == "end":
            ok = list(n.get("outputKeys") or graph_output_keys)
            ag = EndWorkflowAgent(wid, output_keys=ok)
        elif kind == "tool":
            tn = str(n.get("toolName") or "").strip()
            arg_keys = list(n.get("argKeys") or ["task"])
            outk = str(n.get("outputKey") or "").strip() or f"{wid}_output"
            flatten = bool(n.get("flattenOutput", True))
            ag = McpToolWorkflowAgent(
                wid,
                tool_name=tn,
                arg_keys=arg_keys,
                output_key=outk,
                call_tool=call_tool,
                flatten_dict_output=flatten,
            )
        elif kind == "agent":
            ak = str(n.get("agentKey") or "").strip()
            if not ak or ak not in agent_specs_by_key:
                raise ValueError(f"未知 agentKey: {ak!r}（节点 {wid!r}）")
            base = agent_specs_by_key[ak]
            spec = replace(base, key=wid)
            rag = rag_by_agent.get(ak)
            ag = create_llm_mcp_agent(
                spec,
                endpoint=endpoint,
                rag=rag,
                llm=llm,
                model=model,
                temperature=temperature,
            )
        else:
            raise ValueError(f"未支持的节点 kind: {kind!r}（节点 {wid!r}）")
        node_cfgs.append(WorkflowNodeConfig(key=wid, agent=ag, next_keys=nxt if nxt else None))
    cfg = WorkflowConfig(nodes=node_cfgs, entry_key=entry)
    return build_workflow_graph(cfg)


def team_requires_llm(team: TeamSpec) -> bool:
    """
    工业图中若存在 kind=agent 节点、或旧版链式图（全是 Agent），则需要 LLM 客户端。
    仅含 start / tool / end 的工业图可在无 API Key 下编译（仅跑 MCP 工具）。
    """
    g = team.resolved_graph()
    if not g:
        return True
    if is_industrial_graph(g):
        return any(
            str(n.get("kind") or "") == "agent"
            for n in (g.get("nodes") or [])
            if isinstance(n, dict)
        )
    return True


def build_team_mcp_workflow(
    team: TeamSpec,
    *,
    agent_specs_by_key: Mapping[str, AgentSpec],
    endpoint: str | None = None,
    rag_by_agent: Mapping[str, RAGRetriever] | None = None,
    llm: LlmToolChatClient | None = None,
    model: str | None = None,
    temperature: float | None = None,
):
    """
    将 :class:`TeamSpec`（``graph`` 或 ``linear_order``）编译为 LangGraph。

    工作流节点 id 与 Agent 注册 key 可不同；同一 Agent 可在多节点出现（输出写入 ``{nodeId}_output``）。
    """
    g = team.resolved_graph()
    errs = validate_team_graph(g)
    if errs:
        raise ValueError("; ".join(errs))
    if is_industrial_graph(g):
        return _compile_industrial_team_graph(
            g,
            agent_specs_by_key=agent_specs_by_key,
            endpoint=endpoint,
            rag_by_agent=rag_by_agent,
            llm=llm,
            model=model,
            temperature=temperature,
        )
    entry = str(g["entry"]).strip()
    next_map = graph_to_next_map(g)
    rag_by_agent = rag_by_agent or {}
    node_cfgs: list[WorkflowNodeConfig] = []
    for n in g.get("nodes") or []:
        if not isinstance(n, dict):
            continue
        wid = str(n.get("id") or "").strip()
        ak = str(n.get("agentKey") or "").strip()
        if not wid or not ak:
            raise ValueError(f"无效节点: {n!r}")
        if ak not in agent_specs_by_key:
            raise ValueError(f"未知 agentKey: {ak!r}")
        base = agent_specs_by_key[ak]
        spec = replace(base, key=wid)
        rag = rag_by_agent.get(ak)
        agent = create_llm_mcp_agent(
            spec,
            endpoint=endpoint,
            rag=rag,
            llm=llm,
            model=model,
            temperature=temperature,
        )
        nxt = next_map.get(wid) or []
        node_cfgs.append(
            WorkflowNodeConfig(key=wid, agent=agent, next_keys=nxt if nxt else None)
        )
    cfg = WorkflowConfig(nodes=node_cfgs, entry_key=entry)
    return build_workflow_graph(cfg)


def invoke_linear_mcp_team(
    agents: Sequence[AgentSpec],
    *,
    task: str,
    run_id: str = "linear-mcp-team",
    endpoint: str | None = None,
    rag_by_agent: Mapping[str, RAGRetriever] | None = None,
    llm: LlmToolChatClient | None = None,
    model: str | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    """
    一键执行线性团队（演示 / 脚本用）。
    """
    from .runner import run_invocation

    graph = build_linear_mcp_team(
        agents,
        endpoint=endpoint,
        rag_by_agent=rag_by_agent,
        llm=llm,
        model=model,
        temperature=temperature,
    )
    return run_invocation(graph, task=task, run_id=run_id)
