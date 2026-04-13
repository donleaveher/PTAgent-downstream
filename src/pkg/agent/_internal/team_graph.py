"""团队 DAG 校验与 next_map 推导（LangGraph WorkflowConfig）。"""

from __future__ import annotations

from typing import Any, Mapping


def linear_order_to_graph(linear_order: list[str]) -> dict[str, Any] | None:
    """将线性 agent 列表转为图定义（节点 id 为 n0..n{k}）。"""
    lo = [str(x).strip() for x in linear_order if str(x).strip()]
    if not lo:
        return None
    nodes = [{"id": f"n{i}", "agentKey": k} for i, k in enumerate(lo)]
    edges = [{"from": f"n{i}", "to": f"n{i+1}"} for i in range(len(lo) - 1)]
    return {"entry": "n0", "nodes": nodes, "edges": edges}


def is_industrial_graph(g: Mapping[str, Any]) -> bool:
    """工业编排：显式起点/终点，节点可为 agent / tool / start / end。"""
    if g.get("schemaVersion") == 2:
        return True
    for n in g.get("nodes") or []:
        if not isinstance(n, dict):
            continue
        k = (n.get("kind") or "").strip()
        if k in ("start", "end", "tool"):
            return True
    return False


def _dag_cycle_errors(node_ids: set[str], adj: dict[str, list[str]]) -> list[str]:
    errs: list[str] = []
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in node_ids}

    def dfs_cycle(u: str) -> bool:
        color[u] = GRAY
        for v in adj.get(u, []):
            if color.get(v, WHITE) == GRAY:
                return True
            if color.get(v, WHITE) == WHITE and dfs_cycle(v):
                return True
        color[u] = BLACK
        return False

    for nid in node_ids:
        if color[nid] == WHITE and dfs_cycle(nid):
            errs.append("图中存在环路，当前仅支持有向无环图")
            break
    return errs


def validate_legacy_team_graph(g: dict[str, Any]) -> list[str]:
    """仅 Agent 节点（每节点 agentKey）。"""
    errs: list[str] = []
    entry = (g.get("entry") or "").strip()
    nodes_raw = g.get("nodes") or []
    edges_raw = g.get("edges") or []
    if not entry:
        errs.append("graph.entry 不能为空")
        return errs
    node_ids: set[str] = set()
    for n in nodes_raw:
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id") or "").strip()
        ak = str(n.get("agentKey") or "").strip()
        if not nid or not ak:
            errs.append("每个 graph.nodes[] 需要非空 id 与 agentKey")
            continue
        if nid in node_ids:
            errs.append(f"重复节点 id: {nid!r}")
        node_ids.add(nid)
    if entry not in node_ids:
        errs.append(f"entry {entry!r} 不在 nodes 中")
    adj: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for e in edges_raw:
        if not isinstance(e, dict):
            continue
        a = str(e.get("from") or "").strip()
        b = str(e.get("to") or "").strip()
        if not a or not b:
            errs.append("edges 每项需要 from / to")
            continue
        if a not in node_ids or b not in node_ids:
            errs.append(f"边 {a!r}->{b!r} 引用未知节点")
            continue
        adj.setdefault(a, []).append(b)
    errs.extend(_dag_cycle_errors(node_ids, adj))
    return errs


def validate_industrial_graph(g: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    entry = (g.get("entry") or "").strip()
    nodes_raw = [n for n in (g.get("nodes") or []) if isinstance(n, dict)]
    edges_raw = g.get("edges") or []
    if not entry:
        errs.append("graph.entry 不能为空")
        return errs
    if not nodes_raw:
        errs.append("graph.nodes 不能为空")
        return errs

    node_ids: set[str] = set()
    kinds: dict[str, str] = {}
    for n in nodes_raw:
        nid = str(n.get("id") or "").strip()
        kind = str(n.get("kind") or "").strip()
        if not nid:
            errs.append("节点 id 不能为空")
            continue
        if nid in node_ids:
            errs.append(f"重复节点 id: {nid!r}")
            continue
        node_ids.add(nid)
        if not kind:
            errs.append(f"节点 {nid!r} 缺少 kind（start|end|agent|tool）")
            continue
        kinds[nid] = kind
        if kind == "agent":
            if not str(n.get("agentKey") or "").strip():
                errs.append(f"agent 节点 {nid!r} 需要 agentKey")
        elif kind == "tool":
            if not str(n.get("toolName") or "").strip():
                errs.append(f"tool 节点 {nid!r} 需要 toolName")
        elif kind not in ("start", "end"):
            errs.append(f"未知 kind: {kind!r}（节点 {nid!r}）")

    starts = [nid for nid, k in kinds.items() if k == "start"]
    ends = [nid for nid, k in kinds.items() if k == "end"]
    if len(starts) != 1:
        errs.append("必须有且仅有一个 kind=start 的节点")
    if len(ends) != 1:
        errs.append("必须有且仅有一个 kind=end 的节点")
    if len(starts) == 1 and entry != starts[0]:
        errs.append(f"graph.entry 必须为起点节点 id（期望 {starts[0]!r}，当前 {entry!r}）")
    if entry not in node_ids:
        errs.append(f"entry {entry!r} 不在 nodes 中")

    adj: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for e in edges_raw:
        if not isinstance(e, dict):
            continue
        a = str(e.get("from") or "").strip()
        b = str(e.get("to") or "").strip()
        if not a or not b:
            errs.append("edges 每项需要 from / to")
            continue
        if a not in node_ids or b not in node_ids:
            errs.append(f"边 {a!r}->{b!r} 引用未知节点")
            continue
        adj.setdefault(a, []).append(b)

    errs.extend(_dag_cycle_errors(node_ids, adj))

    # 自 entry 可达所有节点，且必须到达 end
    if entry in node_ids and ends:
        seen: set[str] = set()
        stack = [entry]
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            for v in adj.get(u, []):
                stack.append(v)
        if ends[0] not in seen:
            errs.append("从 entry 无法到达结束节点，请检查连线")
        if seen != node_ids:
            errs.append("存在从 entry 不可达的孤立节点")

    return errs


def validate_team_graph(g: dict[str, Any]) -> list[str]:
    """返回错误信息列表；空表示通过。"""
    if is_industrial_graph(g):
        return validate_industrial_graph(g)
    return validate_legacy_team_graph(g)


def graph_to_next_map(g: dict[str, Any]) -> dict[str, list[str]]:
    """由 edges 构建邻接表（出边列表）。"""
    adj: dict[str, list[str]] = {}
    for e in g.get("edges") or []:
        if not isinstance(e, dict):
            continue
        a = str(e.get("from") or "").strip()
        b = str(e.get("to") or "").strip()
        if a and b:
            adj.setdefault(a, []).append(b)
    return adj


def fork_warnings(g: Mapping[str, Any]) -> list[str]:
    """
    同一节点多条出边时：LangGraph 会对下游做 fan-out（并行调度），
    ``state.data`` 为合并字典，同键后写可能覆盖先写。
    """
    warns: list[str] = []
    adj = graph_to_next_map(dict(g))
    for u, outs in sorted(adj.items()):
        if len(outs) > 1:
            warns.append(
                f"节点 {u!r} 有 {len(outs)} 条出边 → 下游并行执行；"
                f"若多路同时写入同一 data 键，结果以引擎合并顺序为准（建议各工具节点使用不同 outputKey）。"
            )
    return warns
