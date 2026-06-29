"""下游统计分析应用服务：差异分析 + 疾病过表达富集 + 跨实验比较。"""

from .cross_experiment import compare_experiments
from .differential_analysis import analyze_experiment_differential
from .enrichment_analysis import run_disease_enrichment

__all__ = [
    "analyze_experiment_differential",
    "compare_experiments",
    "run_disease_enrichment",
]
