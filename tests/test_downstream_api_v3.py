"""§11.1 下游对外 API 测试（FastAPI TestClient + dependency_overrides 注入内存实现）。"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.orchestration import DownstreamPipelineConfig
from pkg.deep_search import EvidenceRecord, EvidenceStance, InMemoryLiteratureSource
from pkg.disease import InMemoryGeneResolver
from pkg.experiment import InMemoryExperimentRepository
from pkg.graph import InMemoryGraphStore
from router.downstream import (
    downstream_router,
    get_graph_store,
    get_pipeline_config,
    get_repository,
)
from tests.pkg.test_experiment_models import valid_payload
from tests.test_pipeline_v3 import EXP, _FakeAnnot, _FakeCTD, _FakeStructure, _seed


def _app(repo, *, graph=None, cfg=None) -> FastAPI:
    app = FastAPI()
    app.include_router(downstream_router)
    app.dependency_overrides[get_repository] = lambda: repo
    if graph is not None:
        app.dependency_overrides[get_graph_store] = lambda: graph
    if cfg is not None:
        app.dependency_overrides[get_pipeline_config] = lambda: cfg
    return app


def _seeded_client() -> tuple[TestClient, InMemoryExperimentRepository]:
    repo = _seed()
    graph = InMemoryGraphStore()
    ctd = _FakeCTD()
    cfg = DownstreamPipelineConfig(
        snapshot_version="1.0",
        pipeline_version="api-test",
        enrichment_min_overlap=1,
        annotation_source=_FakeAnnot(),
        disease_source=ctd,
        structure_provider=_FakeStructure(),
        gene_resolver=InMemoryGeneResolver({"P_HUMAN": "HUMANG"}),
        literature_source=InMemoryLiteratureSource(
            by_disease={"MESH:D007249": [EvidenceRecord(EvidenceStance.SUPPORT, "t", "PMID:1", "lit")]}
        ),
        graph_store=graph,
    )
    return TestClient(_app(repo, graph=graph, cfg=cfg)), repo


def _empty_client() -> tuple[TestClient, InMemoryExperimentRepository]:
    repo = InMemoryExperimentRepository()
    return TestClient(_app(repo)), repo


def test_health() -> None:
    client, _ = _empty_client()
    resp = client.get("/ptagent/api/health")
    assert resp.status_code == 200 and resp.json()["ok"] is True


def test_create_and_get_experiment() -> None:
    client, _ = _empty_client()
    created = client.post("/ptagent/api/experiments", json=valid_payload())
    assert created.status_code == 200, created.text
    eid = created.json()["experiment_id"]

    status = client.get(f"/ptagent/api/experiments/{eid}")
    assert status.status_code == 200
    assert status.json()["experiment_id"] == eid
    assert status.json()["proteins"] >= 1


def test_invalid_bundle_returns_422() -> None:
    client, _ = _empty_client()
    resp = client.post("/ptagent/api/experiments", json={"context": {}, "groups": []})
    assert resp.status_code == 422
    # 结构化报告：可定位字段 + 数量 + 修复指引
    detail = resp.json()["detail"]
    assert detail["error"] == "invalid experiment bundle"
    assert detail["error_count"] >= 1
    assert detail["errors"] and all("location" in e and "message" in e for e in detail["errors"])
    assert "INPUT-CONTRACT" in detail["hint"]


def test_unknown_experiment_returns_404() -> None:
    client, _ = _empty_client()
    assert client.get("/ptagent/api/experiments/nope").status_code == 404
    assert client.get("/ptagent/api/experiments/nope/annotations").status_code == 404
    assert client.get("/ptagent/api/experiments/nope/snapshots").status_code == 404
    assert client.get("/ptagent/api/experiments/nope/reports").status_code == 404


def test_full_flow_via_api() -> None:
    client, _ = _seeded_client()

    # 运行下游管线
    run = client.post(f"/ptagent/api/experiments/{EXP}/pipeline", json={"snapshot_version": "1.0"})
    assert run.status_code == 200, run.text
    body = run.json()
    assert body["completed"] is True
    assert body["steps"]["report"] == "ok"
    assert body["report_checksum"]

    # 查询：注释（按证据等级过滤）/ 差异 / 富集 / 历史
    conc = client.get(
        f"/ptagent/api/experiments/{EXP}/annotations", params={"evidence_level": "CONCLUSION"}
    ).json()
    assert conc["count"] >= 1
    diffs = client.get(
        f"/ptagent/api/experiments/{EXP}/differentials", params={"only_significant": True}
    ).json()
    assert diffs["count"] == 2
    assert client.get(f"/ptagent/api/experiments/{EXP}/enrichments").json()["count"] >= 1
    assert client.get(f"/ptagent/api/experiments/{EXP}/history").json()["count"] >= 1

    # 本次实验 KG：从蛋白 P1 走到疾病（Jak2 → Brain Ischemia 结论）
    kg = client.get(f"/ptagent/api/experiments/{EXP}/kg/proteins/P1/diseases").json()
    assert any(d["disease_key"] == "MESH:D002545" for d in kg["diseases"])

    # 快照 + 报告
    snaps = client.get(f"/ptagent/api/experiments/{EXP}/snapshots").json()
    assert [s["snapshot_version"] for s in snaps["snapshots"]] == ["1.0"]
    report = client.get(
        f"/ptagent/api/experiments/{EXP}/report", params={"snapshot_version": "1.0"}
    ).json()
    assert report["snapshot_version"] == "1.0"
    assert "# 实验报告" in report["markdown"]
    assert len(report["sections"]) == 9

    # 报告 artifact 已落库（§10）：GET /report 返回持久化版本，GET /reports 列出
    assert report["persisted"] is True
    assert report["report_id"]
    reports_list = client.get(f"/ptagent/api/experiments/{EXP}/reports").json()
    assert reports_list["count"] == 1
    assert reports_list["reports"][0]["snapshot_version"] == "1.0"
    assert reports_list["reports"][0]["report_id"] == report["report_id"]
    assert reports_list["reports"][0]["checksum"] == report["checksum"]

    # 重复冻结同版本 → 409（阻止覆盖）
    again = client.post(
        f"/ptagent/api/experiments/{EXP}/freeze",
        json={"snapshot_version": "1.0", "pipeline_version": "x"},
    )
    assert again.status_code == 409


def test_invalid_evidence_level_400() -> None:
    client, _ = _seeded_client()
    resp = client.get(
        f"/ptagent/api/experiments/{EXP}/annotations", params={"evidence_level": "BOGUS"}
    )
    assert resp.status_code == 400


def test_report_unknown_snapshot_404() -> None:
    client, _ = _seeded_client()
    resp = client.get(
        f"/ptagent/api/experiments/{EXP}/report", params={"snapshot_version": "9.9"}
    )
    assert resp.status_code == 404
