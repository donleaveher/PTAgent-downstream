"""结构化实验输入的应用入口。"""

from __future__ import annotations

from typing import Any

from .repository import ExperimentRepository
from .types import ExperimentBundle


def ingest_experiment_bundle(
    bundle: ExperimentBundle,
    repository: ExperimentRepository,
) -> ExperimentBundle:
    """持久化已完成 Pydantic 与跨引用校验的输入三件套。"""

    repository.save_bundle(bundle)
    return bundle


def ingest_experiment_payload(
    payload: dict[str, Any],
    repository: ExperimentRepository,
) -> ExperimentBundle:
    """校验原始 dict 后持久化；校验失败时不调用 repository。"""

    bundle = ExperimentBundle.model_validate(payload)
    return ingest_experiment_bundle(bundle, repository)


__all__ = ["ingest_experiment_bundle", "ingest_experiment_payload"]
