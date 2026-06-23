"""面向新版实验域的标准蛋白注释事实。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class ProteinAnnotationFact:
    """UniProt 等直接数据源返回的一条可溯源事实。"""

    accession: str
    attribute: str
    value: Any
    source_ref: str | None = None
    evidence_code: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ProteinAnnotationSource(Protocol):
    name: str
    version: str

    def fetch(self, accessions: list[str]) -> dict[str, list[ProteinAnnotationFact]]:
        """按 accession 批量返回标准事实；未知 accession 可不出现在结果中。"""

        ...


__all__ = ["ProteinAnnotationFact", "ProteinAnnotationSource"]
