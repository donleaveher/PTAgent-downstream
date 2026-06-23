"""旧 HTTP ExperimentContext 到新版实验领域 Context 的显式转换。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from model.http.pipeline import ExperimentContext as HTTPExperimentContext
from pkg.experiment import ExperimentContext as DomainExperimentContext


@dataclass(frozen=True)
class ExperimentContextMapping:
    """转换结果；领域上下文之外的数据不被静默丢弃或错误塞入 design。"""

    context: DomainExperimentContext
    data_object_ids: tuple[str, ...]
    filter_config: dict[str, Any]
    workflow_preset: dict[str, Any] | None


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _sources(http: HTTPExperimentContext) -> list[dict[str, Any]]:
    """结构化字段优先级：extra.structured_context → extra → constraints。"""

    extra = _mapping(http.extra)
    constraints = _mapping(http.constraints)
    nested = _mapping(extra.get("structured_context"))
    return [nested, extra, constraints]


def _pick(sources: list[dict[str, Any]], *keys: str) -> Any:
    for source in sources:
        for key in keys:
            value = source.get(key)
            if value is not None and value != "":
                return deepcopy(value)
    return None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    raw = value if isinstance(value, (list, tuple, set)) else [value]
    out: list[str] = []
    for item in raw:
        text = str(item).strip()
        if text and text not in out:
            out.append(text)
    return out


def _string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("scientific_name", "scientificName", "name", "label", "value"):
            if value.get(key):
                return str(value[key]).strip()
    return str(value).strip()


def _taxon_id(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, dict):
        value = value.get("taxon_id", value.get("taxonId", value.get("id")))
    return int(value) if value is not None and value != "" else None


def build_raw_experiment_text(http: HTTPExperimentContext) -> str:
    """确定性组合原始背景和研究问题；不进行 LLM 改写。"""

    parts: list[str] = []
    if http.description:
        parts.append(f"实验背景：\n{http.description}")
    if http.hypothesis:
        parts.append(f"研究问题/假设：\n{http.hypothesis}")
    return "\n\n".join(parts)


def _design(http: HTTPExperimentContext, sources: list[dict[str, Any]]) -> dict[str, Any]:
    design = _mapping(_pick(sources, "design", "experiment_design"))
    for key, aliases in (
        ("analysis_mode", ("analysis_mode", "task_type")),
        ("groups", ("groups", "observed_groups")),
        ("samples", ("samples",)),
        ("contrasts", ("contrasts", "comparisons")),
        ("prediction_target", ("prediction_target", "target_cohort")),
    ):
        value = _pick(sources, *aliases)
        if value is not None and key not in design:
            design[key] = value
    if http.hypothesis and "research_hypothesis" not in design:
        design["research_hypothesis"] = http.hypothesis
    if http.constraints:
        design.setdefault("constraints", deepcopy(http.constraints))
    if http.extra:
        design.setdefault("submission_extra", deepcopy(http.extra))
    return design


def map_http_experiment_context(
    http: HTTPExperimentContext,
    *,
    experiment_id: str | None = None,
) -> DomainExperimentContext:
    """把旧 HTTP DTO 映射为新版领域 Context。"""

    sources = _sources(http)
    payload: dict[str, Any] = {
        "session_id": http.session_id,
        "title": http.title,
        "raw_text": build_raw_experiment_text(http),
        "disease": _string_list(_pick(sources, "disease", "diseases")),
        "pathway": _string_list(_pick(sources, "pathway", "pathways")),
        "organism": _string(_pick(sources, "organism", "species")),
        "taxon_id": _taxon_id(_pick(sources, "taxon_id", "taxonId")),
        "assay": _string(_pick(sources, "assay", "assay_type")),
        "design": _design(http, sources),
    }
    if experiment_id is not None:
        payload["experiment_id"] = experiment_id
    return DomainExperimentContext.model_validate(payload)


def map_http_experiment_submission(
    http: HTTPExperimentContext,
    *,
    experiment_id: str | None = None,
) -> ExperimentContextMapping:
    """转换 Context，并显式保留附件引用与旧 Pipeline 执行配置。"""

    return ExperimentContextMapping(
        context=map_http_experiment_context(http, experiment_id=experiment_id),
        data_object_ids=tuple(http.data_object_ids),
        filter_config=http.filter_config.model_dump(mode="json"),
        workflow_preset=(
            http.workflow_preset.model_dump(mode="json") if http.workflow_preset else None
        ),
    )


__all__ = [
    "ExperimentContextMapping",
    "build_raw_experiment_text",
    "map_http_experiment_context",
    "map_http_experiment_submission",
]
