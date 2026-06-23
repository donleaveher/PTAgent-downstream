"""记录不可变原始请求版本，并更新当前结构化 Context 指针。"""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from typing import Any

from model.http.pipeline import ExperimentContext as HTTPExperimentContext
from pkg.experiment import (
    ContextConfirmationStatus,
    ExperimentContext,
    ExperimentContextRevision,
    ExperimentInputArtifact,
    ExperimentRepository,
    ExperimentRequest,
)

from .context_mapper import map_http_experiment_submission


@dataclass(frozen=True)
class RecordedExperimentRequest:
    context: ExperimentContext
    request: ExperimentRequest
    artifacts: tuple[ExperimentInputArtifact, ...]
    revision: ExperimentContextRevision


def _structured_context(context: ExperimentContext) -> dict[str, Any]:
    return {
        "disease": list(context.disease),
        "pathway": list(context.pathway),
        "organism": context.organism,
        "taxon_id": context.taxon_id,
        "assay": context.assay,
        "design": context.design,
    }


def record_http_experiment_request(
    http: HTTPExperimentContext,
    repository: ExperimentRepository,
    *,
    experiment_id: str | None = None,
    submitted_by: str | None = None,
    artifact_metadata: dict[str, dict[str, Any]] | None = None,
    parser_version: str = "context-mapper-v1",
    model_version: str | None = None,
    confirmation_status: ContextConfirmationStatus = ContextConfirmationStatus.PENDING,
    confirmed_by: str | None = None,
    raw_question: str | None = None,
    raw_request_payload: dict[str, Any] | None = None,
) -> RecordedExperimentRequest:
    """将一次 HTTP 提交作为新版本原子追加到 Repository。"""

    mapping = map_http_experiment_submission(http, experiment_id=experiment_id)
    context = mapping.context
    if raw_question is not None:
        raw_question = raw_question.strip()
        if not raw_question:
            raise ValueError("raw_question cannot be empty")
        context = context.model_copy(update={"raw_text": raw_question}, deep=True)
    history = repository.list_requests(context.experiment_id)
    previous = history[-1] if history else None
    request = ExperimentRequest(
        experiment_id=context.experiment_id,
        version=previous.version + 1 if previous else 1,
        raw_question=context.raw_text,
        request_payload=(
            deepcopy(raw_request_payload)
            if raw_request_payload is not None
            else http.model_dump(mode="json")
        ),
        submitted_by=submitted_by,
        supersedes_request_id=previous.request_id if previous else None,
    )

    metadata = artifact_metadata or {}
    artifacts = tuple(
        ExperimentInputArtifact(
            experiment_id=context.experiment_id,
            request_id=request.request_id,
            object_id=object_id,
            input_role=str(metadata.get(object_id, {}).get("input_role") or "unspecified"),
            filename=str(metadata.get(object_id, {}).get("filename") or ""),
            file_hash=metadata.get(object_id, {}).get("file_hash"),
            file_size=metadata.get(object_id, {}).get("file_size"),
            upstream_software=str(
                metadata.get(object_id, {}).get("upstream_software") or ""
            ),
            upstream_version=str(
                metadata.get(object_id, {}).get("upstream_version") or ""
            ),
        )
        for object_id in mapping.data_object_ids
    )
    revision = ExperimentContextRevision(
        experiment_id=context.experiment_id,
        request_id=request.request_id,
        structured_context=_structured_context(context),
        parser_version=parser_version,
        model_version=model_version,
        confirmation_status=confirmation_status,
        confirmed_by=confirmed_by,
    )
    repository.append_request(
        request,
        context=context,
        artifacts=artifacts,
        revision=revision,
    )
    current_context = context.model_copy(
        update={"current_request_id": request.request_id},
        deep=True,
    )
    return RecordedExperimentRequest(
        context=current_context,
        request=request,
        artifacts=artifacts,
        revision=revision,
    )


__all__ = ["RecordedExperimentRequest", "record_http_experiment_request"]
