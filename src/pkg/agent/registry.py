"""Agent / Team 配置的持久化（JSON），供管理界面与脚本共用。"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ._internal.team_graph import linear_order_to_graph, validate_team_graph
from .contracts import AgentSpec


def default_registry_path() -> Path:
    root = Path(__file__).resolve().parents[3]
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    return data / "ptagent_registry.json"


def agent_spec_to_record(spec: AgentSpec) -> dict[str, Any]:
    cats = spec.mcp_categories
    return {
        "key": spec.key,
        "name": spec.name,
        "description": spec.description,
        "mcp_categories": None if cats is None else sorted(cats),
        "system_prompt": spec.system_prompt,
        "rag_profile_id": spec.rag_profile_id,
        "mcp_tool_allowlist": None
        if spec.mcp_tool_allowlist is None
        else sorted(spec.mcp_tool_allowlist),
        "llm_model": spec.llm_model,
        "llm_temperature": spec.llm_temperature,
        "meta": dict(spec.meta),
    }


def record_to_agent_spec(d: Mapping[str, Any]) -> AgentSpec:
    raw = dict(d)
    key = str(raw.get("key") or "").strip()
    if not key:
        raise ValueError("缺少 key")
    cats = raw.get("mcp_categories")
    if cats is None:
        fc: frozenset[str] | None = None
    elif isinstance(cats, list):
        fc = frozenset(str(x) for x in cats)
    else:
        fc = frozenset()
    meta = raw.get("meta")
    al = raw.get("mcp_tool_allowlist")
    if al is None:
        fa: frozenset[str] | None = None
    elif isinstance(al, list):
        fa = frozenset(str(x) for x in al)
    else:
        fa = frozenset()
    lm = str(raw.get("llm_model") or "gpt-4o-mini").strip() or "gpt-4o-mini"
    try:
        lt = float(raw.get("llm_temperature", 0.2))
    except (TypeError, ValueError):
        lt = 0.2
    return AgentSpec(
        key=key,
        name=str(raw.get("name") or ""),
        description=str(raw.get("description") or ""),
        mcp_categories=fc,
        mcp_tool_allowlist=fa,
        system_prompt=str(raw.get("system_prompt") or ""),
        rag_profile_id=raw.get("rag_profile_id") if raw.get("rag_profile_id") is not None else None,
        llm_model=lm,
        llm_temperature=lt,
        meta=dict(meta) if isinstance(meta, dict) else {},
    )


@dataclass
class TeamSpec:
    key: str
    name: str = ""
    linear_order: list[str] = field(default_factory=list)
    #: LangGraph 编排：``entry``、``nodes[{id, agentKey}]``、``edges[{from,to}]``；为空时用 ``linear_order`` 生成链式图
    graph: dict[str, Any] | None = None

    def resolved_graph(self) -> dict[str, Any]:
        if self.graph and isinstance(self.graph, dict) and (self.graph.get("nodes") or []):
            return dict(self.graph)
        lo = [str(x).strip() for x in self.linear_order if str(x).strip()]
        g = linear_order_to_graph(lo)
        if not g:
            raise ValueError("团队缺少有效的 graph 或 linear_order")
        return g


def team_to_record(t: TeamSpec) -> dict[str, Any]:
    out: dict[str, Any] = {
        "key": t.key,
        "name": t.name,
        "linear_order": list(t.linear_order),
    }
    if t.graph:
        out["graph"] = dict(t.graph)
    return out


def record_to_team(d: Mapping[str, Any]) -> TeamSpec:
    raw = dict(d)
    k = str(raw.get("key") or "").strip()
    if not k:
        raise ValueError("team.key 不能为空")
    lo = raw.get("linear_order") or []
    if not isinstance(lo, list):
        lo = []
    linear = [str(x) for x in lo]
    g = raw.get("graph")
    graph: dict[str, Any] | None = None
    if isinstance(g, dict) and (g.get("nodes") or []):
        graph = dict(g)
    return TeamSpec(key=k, name=str(raw.get("name") or ""), linear_order=linear, graph=graph)


class AgentRegistryStore:
    """线程安全的简单 JSON 存储。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or default_registry_path()
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {"version": 1, "agents": {}, "teams": {}}
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {"version": 1, "agents": {}, "teams": {}}
        raw.setdefault("version", 1)
        raw.setdefault("agents", {})
        raw.setdefault("teams", {})
        return raw

    def _save(self, data: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def list_agent_records(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            data = self._load()
            agents = data.get("agents") or {}
            return dict(agents) if isinstance(agents, dict) else {}

    def get_agent_record(self, key: str) -> dict[str, Any] | None:
        return self.list_agent_records().get(key)

    def upsert_agent(self, record: dict[str, Any]) -> None:
        spec = record_to_agent_spec(record)
        key = spec.key
        with self._lock:
            data = self._load()
            agents: dict[str, Any] = data.setdefault("agents", {})
            agents[key] = agent_spec_to_record(spec)
            self._save(data)

    def delete_agent(self, key: str) -> bool:
        with self._lock:
            data = self._load()
            agents: dict[str, Any] = data.setdefault("agents", {})
            if key not in agents:
                return False
            del agents[key]
            # 从团队中移除引用
            teams: dict[str, Any] = data.setdefault("teams", {})
            for tk, tv in list(teams.items()):
                if not isinstance(tv, dict):
                    continue
                lo = tv.get("linear_order") or []
                if isinstance(lo, list) and key in lo:
                    tv["linear_order"] = [x for x in lo if x != key]
                    teams[tk] = tv
            self._save(data)
            return True

    def list_team_records(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            data = self._load()
            teams = data.get("teams") or {}
            return dict(teams) if isinstance(teams, dict) else {}

    def upsert_team(self, record: dict[str, Any]) -> None:
        team = record_to_team(record)
        has_nodes = isinstance(team.graph, dict) and bool(team.graph.get("nodes"))
        has_linear = bool(team.linear_order)
        if has_nodes or has_linear:
            g = team.resolved_graph()
            errs = validate_team_graph(g)
            if errs:
                raise ValueError("; ".join(errs))
        with self._lock:
            data = self._load()
            teams: dict[str, Any] = data.setdefault("teams", {})
            teams[team.key] = team_to_record(team)
            self._save(data)

    def delete_team(self, key: str) -> bool:
        with self._lock:
            data = self._load()
            teams: dict[str, Any] = data.setdefault("teams", {})
            if key not in teams:
                return False
            del teams[key]
            self._save(data)
            return True


# 进程内单例（可测试时替换）
_STORE: AgentRegistryStore | None = None


def get_registry_store() -> AgentRegistryStore:
    global _STORE
    if _STORE is None:
        _STORE = AgentRegistryStore()
    return _STORE
