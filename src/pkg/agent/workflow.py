from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional

from langgraph.graph import END, StateGraph

from ._internal.graph import KernelState, _make_agent_node
from .core import BaseAgent

ConditionFn = Callable[[KernelState], str]


@dataclass
class WorkflowNodeConfig:
    """
    单个节点的编排配置（企业级接口）。

    - key：节点唯一标识（通常等于 agent.name）
    - agent：实现了 BaseAgent 的业务 Agent（LLM Agent、RAG Agent、工具 Agent 等）
    - next_keys：默认顺序流向（无条件直连）
    - condition：可选条件路由函数，返回下一个节点 key
    - conditional_branches：条件值到下游节点的映射
    """

    key: str
    agent: BaseAgent
    next_keys: List[str] | None = None
    condition: Optional[ConditionFn] = None
    conditional_branches: Optional[Dict[str, str]] = None


@dataclass
class WorkflowConfig:
    """
    完整工作流配置。

    - nodes：所有节点配置
    - entry_key：入口节点 key
    """

    nodes: Iterable[WorkflowNodeConfig]
    entry_key: str


def build_workflow_graph(config: WorkflowConfig):
    """
    根据 WorkflowConfig 构建一个支持：
    - 多 Agent（多个 BaseAgent 实例）
    - 条件分支（基于 state 的 ConditionFn）
    的 LangGraph 工作流。
    """

    graph = StateGraph(KernelState)

    node_map: Dict[str, WorkflowNodeConfig] = {}
    for node_cfg in config.nodes:
        if node_cfg.key in node_map:
            raise ValueError(f" duplicated workflow node key: {node_cfg.key}")
        node_map[node_cfg.key] = node_cfg
        graph.add_node(node_cfg.key, _make_agent_node(node_cfg.agent))

    if config.entry_key not in node_map:
        raise ValueError(f"entry_key {config.entry_key!r} not in workflow nodes")

    graph.set_entry_point(config.entry_key)

    for node_cfg in node_map.values():
        if node_cfg.next_keys:
            for nxt in node_cfg.next_keys:
                if nxt not in node_map:
                    raise ValueError(f"next_key {nxt!r} of node {node_cfg.key!r} not in workflow nodes")
                graph.add_edge(node_cfg.key, nxt)

    for node_cfg in node_map.values():
        if node_cfg.condition and node_cfg.conditional_branches:
            graph.add_conditional_edges(
                node_cfg.key,
                node_cfg.condition,
                node_cfg.conditional_branches,
            )

    for key, node_cfg in node_map.items():
        has_outgoing = bool(node_cfg.next_keys) or bool(node_cfg.condition and node_cfg.conditional_branches)
        if not has_outgoing and key != END:
            graph.add_edge(key, END)

    return graph.compile()
