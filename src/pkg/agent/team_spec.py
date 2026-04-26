"""团队编排领域对象（与持久化 dict 的映射见 ``application.agent.records``）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ._internal.team_graph import linear_order_to_graph


@dataclass
class TeamSpec:
    key: str
    name: str = ""
    linear_order: list[str] = field(default_factory=list)
    graph: dict[str, Any] | None = None

    def resolved_graph(self) -> dict[str, Any]:
        if self.graph and isinstance(self.graph, dict) and (self.graph.get("nodes") or []):
            return dict(self.graph)
        lo = [str(x).strip() for x in self.linear_order if str(x).strip()]
        g = linear_order_to_graph(lo)
        if not g:
            raise ValueError("团队缺少有效的 graph 或 linear_order")
        return g


__all__ = ["TeamSpec"]
