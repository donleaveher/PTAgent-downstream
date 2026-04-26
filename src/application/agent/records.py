"""Agent / Team 记录与 dict 映射（产品持久化契约；``TeamSpec`` 定义于 ``pkg.agent.team_spec``）。"""

from __future__ import annotations

from typing import Any, Mapping

from pkg.agent.contracts import AgentSpec
from pkg.agent.team_spec import TeamSpec


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
        "interaction_mode": spec.interaction_mode,
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
    im = str(raw.get("interaction_mode") or "freeform").strip() or "freeform"
    if im not in ("freeform", "structured"):
        im = "freeform"
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
        interaction_mode=im,
        meta=dict(meta) if isinstance(meta, dict) else {},
    )


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


__all__ = [
    "agent_spec_to_record",
    "record_to_agent_spec",
    "record_to_team",
    "team_to_record",
]
