from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Set

from .core import BaseAgent
from .workflow import WorkflowConfig, WorkflowNodeConfig, build_workflow_graph


@dataclass
class PipelineValidationError(Exception):
    code: str
    message: str
    detail: str | None = None

    def __str__(self) -> str:
        if self.detail:
            return f"[{self.code}] {self.message}: {self.detail}"
        return f"[{self.code}] {self.message}"


@dataclass
class PipelineValidationIssue:
    node_key: str | None
    code: str
    reason: str
    detail: str | None = None


@dataclass
class PipelineValidationReport:
    valid: bool
    issues: List[PipelineValidationIssue]


class _NoOpAgent(BaseAgent):
    """仅用于图编译校验的占位 Agent。"""

    def run(self, context, state):  # type: ignore[override]
        return {}


def _build_adjacency(nodes: Iterable[Mapping[str, Any]]) -> Dict[str, Set[str]]:
    adjacency: Dict[str, Set[str]] = {}
    for node in nodes:
        key = str(node["key"])
        adjacency.setdefault(key, set())
        for nxt in node.get("next_keys") or []:
            adjacency[key].add(str(nxt))
        branches = node.get("conditional_branches") or {}
        for target in branches.values():
            adjacency[key].add(str(target))
    return adjacency


def _reachable_from(entry_key: str, adjacency: Mapping[str, Set[str]]) -> Set[str]:
    visited: Set[str] = set()
    stack: List[str] = [entry_key]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        stack.extend(adjacency.get(current, set()) - visited)
    return visited


def _find_cycle(adjacency: Mapping[str, Set[str]], start_nodes: Set[str]) -> List[str]:
    visiting: Set[str] = set()
    visited: Set[str] = set()
    parent: Dict[str, str] = {}

    def dfs(node: str) -> List[str]:
        visiting.add(node)
        for nxt in adjacency.get(node, set()):
            if nxt not in start_nodes:
                continue
            if nxt in visiting:
                cycle = [nxt, node]
                while cycle[-1] != nxt and cycle[-1] in parent:
                    cycle.append(parent[cycle[-1]])
                cycle.reverse()
                return cycle
            if nxt in visited:
                continue
            parent[nxt] = node
            found = dfs(nxt)
            if found:
                return found
        visiting.remove(node)
        visited.add(node)
        return []

    for node in start_nodes:
        if node in visited:
            continue
        cycle = dfs(node)
        if cycle:
            return cycle
    return []


def _has_path(src: str, dst: str, adjacency: Mapping[str, Set[str]]) -> bool:
    if src == dst:
        return True
    visited: Set[str] = set()
    stack: List[str] = [src]
    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        for nxt in adjacency.get(current, set()):
            if nxt == dst:
                return True
            if nxt not in visited:
                stack.append(nxt)
    return False


def validate_pipeline_nodes(
    *,
    entry_key: str,
    nodes: Iterable[Mapping[str, Any]],
) -> None:
    report = check_pipeline_nodes(entry_key=entry_key, nodes=nodes)
    if report.valid:
        return
    first = report.issues[0]
    raise PipelineValidationError(first.code, first.reason, first.detail)


def check_pipeline_nodes(
    *,
    entry_key: str,
    nodes: Iterable[Mapping[str, Any]],
) -> PipelineValidationReport:
    issues: List[PipelineValidationIssue] = []
    node_list = list(nodes)
    if not node_list:
        return PipelineValidationReport(
            valid=False,
            issues=[PipelineValidationIssue(node_key=None, code="PIPELINE_EMPTY", reason="pipeline 必须包含至少一个节点")],
        )

    key_to_node: Dict[str, Mapping[str, Any]] = {}
    for node in node_list:
        key = str(node.get("key") or "")
        if not key:
            issues.append(
                PipelineValidationIssue(
                    node_key=None,
                    code="PIPELINE_INVALID_NODE",
                    reason="节点 key 不能为空",
                )
            )
            continue
        if key in key_to_node:
            issues.append(
                PipelineValidationIssue(
                    node_key=key,
                    code="PIPELINE_DUPLICATE_NODE",
                    reason="存在重复节点 key",
                    detail=repr(key),
                )
            )
            continue
        key_to_node[key] = node

    if not key_to_node:
        return PipelineValidationReport(valid=False, issues=issues)

    if entry_key not in key_to_node:
        issues.append(
            PipelineValidationIssue(
                node_key=None,
                code="PIPELINE_INVALID_ENTRY",
                reason="entry_key 不在节点列表中",
                detail=repr(entry_key),
            )
        )

    for key, node in key_to_node.items():
        next_keys = list(node.get("next_keys") or [])
        branch_map = dict(node.get("conditional_branches") or {})
        condition_key = node.get("condition_key")

        if condition_key and not branch_map:
            issues.append(
                PipelineValidationIssue(
                    node_key=key,
                    code="PIPELINE_INVALID_CONDITION",
                    reason=f"节点 {key!r} 配置了 condition_key 但没有 conditional_branches",
                    detail=repr(condition_key),
                )
            )
        if branch_map and not condition_key:
            issues.append(
                PipelineValidationIssue(
                    node_key=key,
                    code="PIPELINE_INVALID_CONDITION",
                    reason=f"节点 {key!r} 配置了 conditional_branches 但没有 condition_key",
                )
            )

        for nxt in next_keys:
            if nxt not in key_to_node:
                issues.append(
                    PipelineValidationIssue(
                        node_key=key,
                        code="PIPELINE_INVALID_NEXT",
                        reason=f"节点 {key!r} 的 next_key 指向未知节点",
                        detail=repr(nxt),
                    )
                )
        for branch_value, target in branch_map.items():
            if target not in key_to_node:
                issues.append(
                    PipelineValidationIssue(
                        node_key=key,
                        code="PIPELINE_INVALID_BRANCH",
                        reason=f"节点 {key!r} 的条件分支指向未知节点",
                        detail=f"value={branch_value!r}, target={target!r}",
                    )
                )

    adjacency = _build_adjacency(key_to_node.values())
    reachable = _reachable_from(entry_key, adjacency) if entry_key in key_to_node else set()
    unreachable = sorted(set(key_to_node) - reachable)
    for node_key in unreachable:
        issues.append(
            PipelineValidationIssue(
                node_key=node_key,
                code="PIPELINE_UNREACHABLE_NODE",
                reason="存在无法从 entry_key 到达的节点",
                detail=f"entry_key={entry_key!r}",
            )
        )

    cycle = _find_cycle(adjacency, reachable) if reachable else []
    if cycle:
        for node_key in sorted(set(cycle)):
            issues.append(
                PipelineValidationIssue(
                    node_key=node_key,
                    code="PIPELINE_DEADLOCK",
                    reason="检测到可能导致死锁的环路",
                    detail=" -> ".join(cycle),
                )
            )

    for key, node in key_to_node.items():
        params = node.get("params") or {}
        depends_on = params.get("depends_on") if isinstance(params, Mapping) else None
        if depends_on is None:
            continue
        if not isinstance(depends_on, list):
            issues.append(
                PipelineValidationIssue(
                    node_key=key,
                    code="PIPELINE_INVALID_DEPENDENCY",
                    reason=f"节点 {key!r} 的 params.depends_on 必须是数组",
                )
            )
            continue
        for dep in depends_on:
            dep_key = str(dep)
            if dep_key not in key_to_node:
                issues.append(
                    PipelineValidationIssue(
                        node_key=key,
                        code="PIPELINE_INVALID_DEPENDENCY",
                        reason=f"节点 {key!r} 依赖了不存在的节点",
                        detail=repr(dep_key),
                    )
                )
                continue
            if dep_key == key:
                issues.append(
                    PipelineValidationIssue(
                        node_key=key,
                        code="PIPELINE_INVALID_DEPENDENCY",
                        reason=f"节点 {key!r} 不能依赖自己",
                    )
                )
                continue
            if not _has_path(dep_key, key, adjacency):
                issues.append(
                    PipelineValidationIssue(
                        node_key=key,
                        code="PIPELINE_INVALID_DEPENDENCY",
                        reason=f"节点 {key!r} 的依赖在拓扑上无法先于当前节点执行",
                        detail=f"depends_on={dep_key!r}",
                    )
                )

    workflow_nodes: List[WorkflowNodeConfig] = []
    for key, node in key_to_node.items():
        workflow_nodes.append(
            WorkflowNodeConfig(
                key=key,
                agent=_NoOpAgent(name=key),
                next_keys=list(node.get("next_keys") or []),
                condition=(lambda _state: "default") if node.get("condition_key") else None,
                conditional_branches=dict(node.get("conditional_branches") or {}) or None,
            )
        )

    try:
        build_workflow_graph(WorkflowConfig(nodes=workflow_nodes, entry_key=entry_key))
    except Exception as exc:  # noqa: BLE001
        issues.append(
            PipelineValidationIssue(
                node_key=None,
                code="PIPELINE_INVALID_GRAPH",
                reason="LangGraph 图编译失败，pipeline 定义不合法",
                detail=str(exc),
            )
        )

    return PipelineValidationReport(valid=not issues, issues=issues)


__all__ = [
    "PipelineValidationError",
    "PipelineValidationIssue",
    "PipelineValidationReport",
    "validate_pipeline_nodes",
    "check_pipeline_nodes",
]
