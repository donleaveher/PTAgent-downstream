"""LangGraph 状态与编译：包内实现细节，不通过 ``pkg.agent`` 根导出。"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, TypedDict

from langgraph.graph import END, StateGraph

from ..core import BaseAgent, RunContext


class KernelState(TypedDict, total=False):
    """LangGraph 共享状态：context / data / logs。"""

    context: RunContext
    data: Dict[str, Any]
    logs: List[str]


def _make_agent_node(agent: BaseAgent):
    """将 BaseAgent 封装为 LangGraph 节点函数。"""

    def node_fn(state: KernelState) -> Dict[str, Any]:
        context = state.get("context")
        if context is None:
            raise RuntimeError(f"RunContext 丢失，无法执行 Agent：{agent}")

        delta = agent.run(context=context, state=state)

        logs = list(state.get("logs") or [])
        logs.append(f"Agent {agent.name} executed.")

        return {
            **delta,
            "logs": logs,
        }

    return node_fn


def build_linear_agent_graph(agents: Iterable[BaseAgent]):
    """顺序串联多个 BaseAgent，返回已编译图。"""
    graph = StateGraph(KernelState)

    agent_list = list(agents)
    if not agent_list:
        raise ValueError("构建 Graph 至少需要一个 Agent。")

    for agent in agent_list:
        graph.add_node(agent.name, _make_agent_node(agent))

    first_name = agent_list[0].name
    graph.set_entry_point(first_name)

    for current, nxt in zip(agent_list, agent_list[1:]):
        graph.add_edge(current.name, nxt.name)

    graph.add_edge(agent_list[-1].name, END)

    return graph.compile()
