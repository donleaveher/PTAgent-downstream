"""定量摄入服务 + API 测试（下游自定义契约 §6）。

覆盖：校验通过并落库往返 / 坏引用整批拦截 / 行内 experiment_id 不匹配 /
幂等 upsert / 未知实验 404 / 字段缺失 422。
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.experiment.quantification_ingest import (
    QuantificationIngestError,
    ingest_experiment_quantifications,
)
from pkg.experiment import (
    ExperimentBundle,
    ExperimentContext,
    ExperimentGroup,
    GroupRole,
    InMemoryExperimentRepository,
    ProteinRecord,
)
from router.downstream import downstream_router, get_repository

EXP = "exp_quant"


def _seed() -> InMemoryExperimentRepository:
    repo = InMemoryExperimentRepository()
    repo.save_bundle(
        ExperimentBundle(
            context=ExperimentContext(experiment_id=EXP, raw_text="ischemia", organism="rat"),
            groups=[
                ExperimentGroup(group_id="g_case", label="Case", role=GroupRole.CASE),
                ExperimentGroup(group_id="g_ctrl", label="Control", role=GroupRole.CONTROL),
            ],
            proteins=[
                ProteinRecord(protein_id="prot1", accession="P1", gene="Jak2"),
                ProteinRecord(protein_id="prot2", accession="P2", gene="Stat3"),
            ],
            peptides=[],
        )
    )
    return repo


def _rows() -> list[dict]:
    return [
        {"protein_id": "prot1", "group_id": "g_case", "sample_id": "c1", "abundance": 101.0},
        {"protein_id": "prot1", "group_id": "g_ctrl", "sample_id": "k1", "abundance": 11.0},
        {"protein_id": "prot2", "group_id": "g_case", "sample_id": "c1", "abundance": 80.0},
    ]


def _client(repo: InMemoryExperimentRepository) -> TestClient:
    app = FastAPI()
    app.include_router(downstream_router)
    app.dependency_overrides[get_repository] = lambda: repo
    return TestClient(app)


# ---------------- 服务层 ----------------
def test_ingest_valid_rows_persists_roundtrip() -> None:
    repo = _seed()
    summary = ingest_experiment_quantifications(EXP, _rows(), repository=repo)
    assert summary == {
        "experiment_id": EXP,
        "received": 3,
        "written": 3,
        "proteins": 2,
        "groups": 2,
        "samples": 2,
    }
    stored = repo.list_quantifications(EXP)
    assert len(stored) == 3
    assert all(q.experiment_id == EXP for q in stored)
    # experiment_id 由路径注入，落库行携带它。
    assert {(q.protein_id, q.group_id, q.sample_id) for q in stored} == {
        ("prot1", "g_case", "c1"),
        ("prot1", "g_ctrl", "k1"),
        ("prot2", "g_case", "c1"),
    }


def test_unknown_protein_rejects_whole_batch() -> None:
    repo = _seed()
    rows = _rows() + [
        {"protein_id": "ghost", "group_id": "g_case", "sample_id": "c9", "abundance": 1.0}
    ]
    with pytest.raises(QuantificationIngestError, match="unknown protein_id 'ghost'"):
        ingest_experiment_quantifications(EXP, rows, repository=repo)
    # 整批拒绝：合法行也不落库。
    assert repo.list_quantifications(EXP) == []


def test_unknown_group_rejects_whole_batch() -> None:
    repo = _seed()
    rows = [{"protein_id": "prot1", "group_id": "g_bogus", "sample_id": "c1", "abundance": 1.0}]
    with pytest.raises(QuantificationIngestError, match="unknown group_id 'g_bogus'"):
        ingest_experiment_quantifications(EXP, rows, repository=repo)


def test_row_experiment_id_mismatch_rejected() -> None:
    repo = _seed()
    rows = [
        {
            "experiment_id": "other_exp",
            "protein_id": "prot1",
            "group_id": "g_case",
            "sample_id": "c1",
            "abundance": 1.0,
        }
    ]
    with pytest.raises(QuantificationIngestError, match="does not match"):
        ingest_experiment_quantifications(EXP, rows, repository=repo)


def test_missing_abundance_is_validation_error() -> None:
    repo = _seed()
    rows = [{"protein_id": "prot1", "group_id": "g_case", "sample_id": "c1"}]
    with pytest.raises(QuantificationIngestError, match="abundance"):
        ingest_experiment_quantifications(EXP, rows, repository=repo)


def test_resubmit_same_triple_upserts() -> None:
    repo = _seed()
    ingest_experiment_quantifications(EXP, _rows(), repository=repo)
    ingest_experiment_quantifications(
        EXP,
        [{"protein_id": "prot1", "group_id": "g_case", "sample_id": "c1", "abundance": 999.0}],
        repository=repo,
    )
    stored = repo.list_quantifications(EXP)
    assert len(stored) == 3  # 未新增，同三元组被覆盖
    updated = next(
        q for q in stored if (q.protein_id, q.group_id, q.sample_id) == ("prot1", "g_case", "c1")
    )
    assert updated.abundance == 999.0


def test_unknown_experiment_raises_value_error() -> None:
    repo = _seed()
    with pytest.raises(ValueError, match="unknown experiment_id"):
        ingest_experiment_quantifications("nope", _rows(), repository=repo)


# ---------------- API 层 ----------------
def test_api_ingest_then_list_roundtrip() -> None:
    repo = _seed()
    client = _client(repo)
    resp = client.post(
        f"/ptagent/api/experiments/{EXP}/quantifications", json={"quantifications": _rows()}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["written"] == 3

    listed = client.get(f"/ptagent/api/experiments/{EXP}/quantifications")
    assert listed.status_code == 200
    assert listed.json()["count"] == 3


def test_api_bad_reference_returns_422() -> None:
    repo = _seed()
    client = _client(repo)
    resp = client.post(
        f"/ptagent/api/experiments/{EXP}/quantifications",
        json={"quantifications": [
            {"protein_id": "ghost", "group_id": "g_case", "sample_id": "c1", "abundance": 1.0}
        ]},
    )
    assert resp.status_code == 422
    assert "unknown protein_id" in resp.text


def test_api_missing_field_returns_422() -> None:
    repo = _seed()
    client = _client(repo)
    resp = client.post(
        f"/ptagent/api/experiments/{EXP}/quantifications",
        json={"quantifications": [{"protein_id": "prot1", "group_id": "g_case", "sample_id": "c1"}]},
    )
    assert resp.status_code == 422  # FastAPI body 校验：缺 abundance


def test_api_unknown_experiment_returns_404() -> None:
    repo = _seed()
    client = _client(repo)
    resp = client.post(
        "/ptagent/api/experiments/nope/quantifications", json={"quantifications": _rows()}
    )
    assert resp.status_code == 404
    assert client.get("/ptagent/api/experiments/nope/quantifications").status_code == 404
