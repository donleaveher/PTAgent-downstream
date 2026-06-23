"""不可变原始请求版本、附件绑定和当前 Context 指针。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from application.experiment import (
    map_http_experiment_context,
    record_http_experiment_request,
)
from model.http.pipeline import ExperimentContext as HTTPExperimentContext
from pkg.experiment import (
    ContextConfirmationStatus,
    ExperimentRequest,
    ExperimentContextRevision,
    InMemoryExperimentRepository,
    RequestVersionConflict,
)


def _http(hypothesis: str = "预测非健康人蛋白变化") -> HTTPExperimentContext:
    return HTTPExperimentContext(
        session_id="sess_1",
        title="跨物种预测",
        description="健康小鼠、非健康小鼠和健康人蛋白质组",
        hypothesis=hypothesis,
        data_object_ids=["dobj_protein", "dobj_peptide"],
        extra={
            "structured_context": {
                "analysis_mode": "cross_species_prediction",
                "observed_groups": [
                    {"species": "mouse", "condition": "healthy"},
                    {"species": "mouse", "condition": "disease"},
                    {"species": "human", "condition": "healthy"},
                ],
                "prediction_target": {"species": "human", "condition": "disease"},
            }
        },
    )


def test_first_request_records_raw_payload_artifacts_and_revision() -> None:
    repo = InMemoryExperimentRepository()
    recorded = record_http_experiment_request(
        _http(),
        repo,
        experiment_id="exp_1",
        submitted_by="user_1",
        artifact_metadata={
            "dobj_protein": {
                "input_role": "protein_table",
                "filename": "proteins.tsv",
                "file_hash": "sha-protein",
            },
            "dobj_peptide": {
                "input_role": "peptide_table",
                "filename": "peptides.tsv",
                "file_hash": "sha-peptide",
            },
        },
        parser_version="context-mapper-v1",
    )

    request = recorded.request
    assert request.version == 1
    assert request.supersedes_request_id is None
    assert len(request.content_hash) == 64
    assert request.request_payload["hypothesis"] == "预测非健康人蛋白变化"
    assert repo.get_current_request("exp_1") == request
    assert repo.get_context("exp_1").current_request_id == request.request_id
    artifacts = repo.list_input_artifacts(request.request_id)
    assert [(a.object_id, a.input_role) for a in artifacts] == [
        ("dobj_protein", "protein_table"),
        ("dobj_peptide", "peptide_table"),
    ]
    revisions = repo.list_context_revisions(request.request_id)
    assert revisions == [recorded.revision]
    assert revisions[0].structured_context["design"]["analysis_mode"] == (
        "cross_species_prediction"
    )


def test_second_submission_appends_version_and_preserves_v1() -> None:
    repo = InMemoryExperimentRepository()
    first = record_http_experiment_request(_http(), repo, experiment_id="exp_1")
    second = record_http_experiment_request(
        _http("只预测人脑组织中的蛋白变化"),
        repo,
        experiment_id="exp_1",
    )

    history = repo.list_requests("exp_1")
    assert [request.version for request in history] == [1, 2]
    assert second.request.supersedes_request_id == first.request.request_id
    assert history[0] == first.request
    assert history[0].raw_question != history[1].raw_question
    assert repo.get_current_request("exp_1") == second.request
    assert repo.get_request(first.request.request_id) == first.request


def test_request_model_is_frozen_and_hash_is_verified() -> None:
    request = ExperimentRequest(
        experiment_id="exp_1",
        version=1,
        raw_question="原始问题",
        request_payload={"question": "原始问题"},
    )
    with pytest.raises(ValidationError):
        request.raw_question = "覆盖问题"
    with pytest.raises(ValidationError, match="content_hash does not match"):
        ExperimentRequest(
            experiment_id="exp_1",
            version=1,
            raw_question="原始问题",
            request_payload={},
            content_hash="0" * 64,
        )


def test_repository_rejects_skipped_version() -> None:
    repo = InMemoryExperimentRepository()
    first = record_http_experiment_request(_http(), repo, experiment_id="exp_1")
    context = map_http_experiment_context(
        _http("第三版问题"),
        experiment_id="exp_1",
    )
    skipped = ExperimentRequest(
        experiment_id="exp_1",
        version=3,
        raw_question=context.raw_text,
        request_payload={},
        supersedes_request_id=first.request.request_id,
    )
    with pytest.raises(RequestVersionConflict, match="expected request version 2"):
        repo.append_request(skipped, context=context)


def test_confirmed_revision_requires_actor() -> None:
    with pytest.raises(ValidationError, match="requires confirmed_by"):
        record_http_experiment_request(
            _http(),
            InMemoryExperimentRepository(),
            experiment_id="exp_1",
            confirmation_status=ContextConfirmationStatus.CONFIRMED,
        )


def test_raw_payload_override_preserves_router_input_exactly() -> None:
    repo = InMemoryExperimentRepository()
    raw_payload = {
        "description": "原始描述",
        "hypothesis": "原始问题",
        "future_unknown_field": {"keep": True},
    }
    recorded = record_http_experiment_request(
        _http(),
        repo,
        experiment_id="exp_1",
        raw_question="用户提交的完整原始文本",
        raw_request_payload=raw_payload,
    )
    raw_payload["future_unknown_field"]["keep"] = False
    assert recorded.request.raw_question == "用户提交的完整原始文本"
    assert recorded.request.request_payload["future_unknown_field"] == {"keep": True}
    assert repo.get_context("exp_1").raw_text == "用户提交的完整原始文本"


def test_context_revisions_are_append_only() -> None:
    repo = InMemoryExperimentRepository()
    recorded = record_http_experiment_request(_http(), repo, experiment_id="exp_1")
    confirmed = ExperimentContextRevision(
        revision_id="ctxrev_confirmed",
        experiment_id="exp_1",
        request_id=recorded.request.request_id,
        structured_context=recorded.revision.structured_context,
        parser_version="context-mapper-v1",
        confirmation_status=ContextConfirmationStatus.CONFIRMED,
        confirmed_by="user_1",
    )
    repo.append_context_revision(confirmed)
    revisions = repo.list_context_revisions(recorded.request.request_id)
    assert [row.confirmation_status for row in revisions] == [
        ContextConfirmationStatus.PENDING,
        ContextConfirmationStatus.CONFIRMED,
    ]
    assert revisions[0] == recorded.revision


def test_raw_question_whitespace_is_stripped_consistently() -> None:
    repo = InMemoryExperimentRepository()
    recorded = record_http_experiment_request(
        _http(),
        repo,
        experiment_id="exp_1",
        raw_question="  用户提交的完整原始文本\n",
    )
    assert recorded.request.raw_question == "用户提交的完整原始文本"
    assert recorded.context.raw_text == "用户提交的完整原始文本"
    assert repo.get_context("exp_1").raw_text == "用户提交的完整原始文本"


def test_duplicate_artifact_object_role_is_rejected() -> None:
    repo = InMemoryExperimentRepository()
    http = _http()
    http.data_object_ids = ["dobj_dup", "dobj_dup"]
    with pytest.raises(ValueError, match="duplicate object_id/input_role"):
        record_http_experiment_request(http, repo, experiment_id="exp_1")


def test_created_at_is_preserved_across_request_versions() -> None:
    repo = InMemoryExperimentRepository()
    record_http_experiment_request(_http(), repo, experiment_id="exp_1")
    created = repo.get_context("exp_1").created_at
    record_http_experiment_request(_http("第二版问题"), repo, experiment_id="exp_1")
    assert repo.get_context("exp_1").created_at == created
