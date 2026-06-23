"""分层报告应用服务（从冻结快照生成可审计报告）。"""

from .layered_report import ExperimentReport, generate_experiment_report

__all__ = ["ExperimentReport", "generate_experiment_report"]
