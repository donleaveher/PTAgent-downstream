"""§11.2 下游 LangGraph 主图测试：复用 step + 共享状态 + 人审批条件边 + audit log。"""
from __future__ import annotations

from application.orchestration.graph import (
    build_downstream_graph,
    run_downstream_graph,
)
from application.orchestration.graph import _route_after_approval  # noqa: PLC2701
from tests.test_pipeline_v3 import EXP, _full_config, _seed

_STEP_NODES = {
    "import", "base_annotation", "ctd_disease", "differential", "enrichment",
    "hypothesis", "kg_projection", "deep_search", "freeze", "report",
}


def test_graph_approve_runs_full_flow() -> None:
    repo = _seed()
    result = run_downstream_graph(EXP, repository=repo, config=_full_config(), human_action="approve")

    assert result.completed is True
    assert result.failed_step is None
    statuses = result.step_statuses()
    assert set(statuses) == _STEP_NODES
    assert statuses["report"] == "ok" and statuses["freeze"] == "ok"
    assert statuses["import"] == "skipped"  # 预导入

    # 人审批留痕 + 报告 + 快照
    assert "human_approval: approve" in result.audit_log
    assert result.report is not None
    assert [s.snapshot_version for s in repo.list_snapshots(EXP)] == ["1.0"]


def test_graph_reject_stops_before_freeze() -> None:
    repo = _seed()
    result = run_downstream_graph(EXP, repository=repo, config=_full_config(), human_action="reject")

    assert result.completed is False
    assert result.failed_step is None
    statuses = result.step_statuses()
    assert "freeze" not in statuses and "report" not in statuses
    assert statuses["deep_search"] == "ok"
    assert "human_approval: reject" in result.audit_log
    assert repo.list_snapshots(EXP) == []  # 未冻结


def test_graph_modify_stops_before_freeze() -> None:
    repo = _seed()
    result = run_downstream_graph(EXP, repository=repo, config=_full_config(), human_action="modify")
    assert result.completed is False
    assert "freeze" not in result.step_statuses()
    assert "human_approval: modify" in result.audit_log
    assert repo.list_snapshots(EXP) == []


def test_graph_failure_is_isolated() -> None:
    repo = _seed()
    # deep_search 无文献源 → 失败；下游 human_approval/freeze/report 跳过
    result = run_downstream_graph(
        EXP, repository=repo, config=_full_config(literature_source=None), human_action="approve"
    )
    assert result.completed is False
    assert result.failed_step == "deep_search"
    statuses = result.step_statuses()
    assert statuses["deep_search"] == "failed"
    assert "freeze" not in statuses and "report" not in statuses
    assert repo.list_snapshots(EXP) == []


def test_route_after_approval_unit() -> None:
    assert _route_after_approval({"human_action": "approve"}) == "approve"
    assert _route_after_approval({"human_action": "modify"}) == "modify"
    assert _route_after_approval({"human_action": "reject"}) == "reject"
    assert _route_after_approval({"human_action": "bogus"}) == "reject"
    assert _route_after_approval({"human_action": "approve", "failed_step": "x"}) == "reject"


def test_build_graph_compiles_with_nodes() -> None:
    graph = build_downstream_graph()
    assert hasattr(graph, "invoke")
    node_names = set(graph.get_graph().nodes)
    assert _STEP_NODES | {"human_approval"} <= node_names
