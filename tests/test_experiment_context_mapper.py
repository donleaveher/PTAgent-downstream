"""旧 HTTP ExperimentContext → 新版领域 Context 映射。"""

from __future__ import annotations

from application.experiment import (
    build_raw_experiment_text,
    map_http_experiment_context,
    map_http_experiment_submission,
)
from model.http.pipeline import ExperimentContext, ToolPresetBinding, WorkflowPreset


def _http_context() -> ExperimentContext:
    return ExperimentContext(
        session_id="sess_1",
        title="跨物种疾病预测",
        description="健康小鼠、非健康小鼠和健康人的蛋白质组。",
        hypothesis="根据非健康小鼠预测非健康人可能变化的蛋白。",
        data_object_ids=["dobj_protein", "dobj_peptide"],
        constraints={"species": "constraint-species", "max_runtime": 3600},
        extra={
            "species": "Rattus norvegicus",
            "taxon_id": "10116",
            "assay": "DIA",
            "structured_context": {
                "diseases": ["CIRI"],
                "pathways": "JAK2/STAT3",
                "analysis_mode": "cross_species_prediction",
                "observed_groups": [
                    {"species": "mouse", "condition": "healthy"},
                    {"species": "mouse", "condition": "disease"},
                    {"species": "human", "condition": "healthy"},
                ],
                "prediction_target": {"species": "human", "condition": "disease"},
            },
        },
    )


def test_build_raw_text_is_deterministic_and_unmodified() -> None:
    http = _http_context()
    assert build_raw_experiment_text(http) == (
        "实验背景：\n健康小鼠、非健康小鼠和健康人的蛋白质组。\n\n"
        "研究问题/假设：\n根据非健康小鼠预测非健康人可能变化的蛋白。"
    )


def test_maps_http_context_to_domain_context() -> None:
    mapped = map_http_experiment_context(_http_context(), experiment_id="exp_1")
    assert mapped.experiment_id == "exp_1"
    assert mapped.session_id == "sess_1"
    assert mapped.title == "跨物种疾病预测"
    assert mapped.disease == ["CIRI"]
    assert mapped.pathway == ["JAK2/STAT3"]
    assert mapped.organism == "Rattus norvegicus"
    assert mapped.taxon_id == 10116
    assert mapped.assay == "DIA"
    assert mapped.design["analysis_mode"] == "cross_species_prediction"
    assert len(mapped.design["groups"]) == 3
    assert mapped.design["prediction_target"] == {
        "species": "human",
        "condition": "disease",
    }
    assert mapped.design["research_hypothesis"] == _http_context().hypothesis


def test_structured_extra_has_priority_over_constraints() -> None:
    http = _http_context()
    mapped = map_http_experiment_context(http)
    assert mapped.organism == "Rattus norvegicus"
    assert mapped.organism != http.constraints["species"]


def test_submission_mapping_preserves_non_domain_inputs() -> None:
    http = _http_context()
    http.workflow_preset = WorkflowPreset(
        preset_key="knowledge-v3",
        tool_bindings=[
            ToolPresetBinding(step_id="annot", tool_name="get_protein_annotations")
        ],
    )
    mapped = map_http_experiment_submission(http, experiment_id="exp_1")
    assert mapped.data_object_ids == ("dobj_protein", "dobj_peptide")
    assert mapped.filter_config["enabled"] is True
    assert mapped.workflow_preset is not None
    assert mapped.workflow_preset["preset_key"] == "knowledge-v3"
    assert "data_object_ids" not in mapped.context.model_fields_set


def test_mapper_does_not_mutate_http_extra_or_constraints() -> None:
    http = _http_context()
    original_extra = http.extra.copy()
    original_constraints = http.constraints.copy()
    mapped = map_http_experiment_context(http)
    mapped.design["submission_extra"]["species"] = "changed"
    assert http.extra == original_extra
    assert http.constraints == original_constraints
