"""下游统计分析：差异分析 + 过表达富集（纯函数引擎）。"""

from pkg.analysis.differential import compute_differential_results
from pkg.analysis.enrichment import EnrichmentResult, over_representation

__all__ = [
    "EnrichmentResult",
    "compute_differential_results",
    "over_representation",
]
