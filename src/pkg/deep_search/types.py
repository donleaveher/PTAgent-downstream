"""Deep-search（认知态跃迁，L4）的任务、证据与可注入检索源协议。

对一条蛋白级疾病**假说**（M3 产物，`MetaAnnotation(HYPOTHESIS)`）发起在线检索，
按返回证据的立场推动 `假说 → 结论/伪理/保持`。检索源（DeepXiv/文献 MCP 等）是外部
依赖，统一抽象为 :class:`LiteratureSearchSource` 协议——真实工具后接，禁止把 Mock 证据
当生产源（§8.1）。状态机本身是纯函数（见 :mod:`pkg.deep_search.verdict`）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class EvidenceStance(str, Enum):
    """一条证据相对假说的立场。"""

    SUPPORT = "support"   # 直接支持假说（→ 倾向结论）
    REFUTE = "refute"     # 反证（→ 倾向伪理）
    NEUTRAL = "neutral"   # 相关但不足以判定


@dataclass(frozen=True)
class DeepSearchTask:
    """对一条假说发起的检索任务（面向 蛋白/基因 × 疾病 × 实验背景）。"""

    annotation_id: str
    experiment_id: str
    protein_id: str
    gene: str
    disease_id: str
    disease_name: str
    organism: str = ""
    taxon_id: int | None = None
    tissue: str = ""
    background: str = ""
    query: str = ""  # 规范化查询串（确定性，便于溯源/复跑）


@dataclass(frozen=True)
class EvidenceRecord:
    """一条检索证据：带立场与可溯源引用。"""

    stance: EvidenceStance
    title: str
    reference: str  # 稳定引用，如 PMID / DOI / URL
    source: str     # 检索工具名
    snippet: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class LiteratureSearchSource(Protocol):
    name: str
    version: str

    def search(self, task: DeepSearchTask) -> list[EvidenceRecord]:
        """对一条任务返回证据列表（可空 = 无结果）。失败/超时由实现决定抛错或返回空。"""

        ...


__all__ = [
    "DeepSearchTask",
    "EvidenceRecord",
    "EvidenceStance",
    "LiteratureSearchSource",
]
