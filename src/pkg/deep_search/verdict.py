"""Deep-search 状态机（纯函数，L4 §8.2）。

把一组证据裁决成对假说证据等级的跃迁：

- 仅支持证据 → ``SUPPORTED`` → `CONCLUSION`
- 仅反证 → ``REFUTED`` → `REFUTED`（负结果不删除，显式落库）
- 既有支持又有反证 → ``CONFLICTING`` → 保持 `HYPOTHESIS`（冲突未决，不冒进任一方）
- 无充分证据 → ``INSUFFICIENT`` → 保持 `HYPOTHESIS`（显式记录未决）

纯函数、确定性，便于独立测试；落库与历史追加由应用服务负责。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from pkg.deep_search.types import EvidenceRecord, EvidenceStance
from pkg.experiment import EvidenceLevel


class DeepSearchVerdict(str, Enum):
    SUPPORTED = "supported"
    REFUTED = "refuted"
    CONFLICTING = "conflicting"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class VerdictOutcome:
    verdict: DeepSearchVerdict
    to_level: EvidenceLevel
    changed: bool                      # to_level 是否相对当前等级发生跃迁
    support_refs: tuple[str, ...]
    refute_refs: tuple[str, ...]


def decide_verdict(
    current_level: EvidenceLevel, evidence: Sequence[EvidenceRecord]
) -> VerdictOutcome:
    """根据证据立场裁决目标等级（不落库）。"""

    support_refs = tuple(
        sorted(e.reference for e in evidence if e.stance is EvidenceStance.SUPPORT)
    )
    refute_refs = tuple(
        sorted(e.reference for e in evidence if e.stance is EvidenceStance.REFUTE)
    )

    if support_refs and not refute_refs:
        verdict, to_level = DeepSearchVerdict.SUPPORTED, EvidenceLevel.CONCLUSION
    elif refute_refs and not support_refs:
        verdict, to_level = DeepSearchVerdict.REFUTED, EvidenceLevel.REFUTED
    elif support_refs and refute_refs:
        verdict, to_level = DeepSearchVerdict.CONFLICTING, EvidenceLevel.HYPOTHESIS
    else:
        verdict, to_level = DeepSearchVerdict.INSUFFICIENT, EvidenceLevel.HYPOTHESIS

    return VerdictOutcome(
        verdict=verdict,
        to_level=to_level,
        changed=to_level is not current_level,
        support_refs=support_refs,
        refute_refs=refute_refs,
    )


__all__ = ["DeepSearchVerdict", "VerdictOutcome", "decide_verdict"]
