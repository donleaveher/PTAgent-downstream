"""§11.1 鉴权 + 审计测试：JWT gate 默认关闭(开放)、启用后无/坏 token → 401、审计日志。"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from pkg.experiment import InMemoryExperimentRepository
from router.downstream import authorize, downstream_router, get_repository


def _client(repo: InMemoryExperimentRepository | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(downstream_router)
    app.dependency_overrides[get_repository] = lambda: repo or InMemoryExperimentRepository()
    return TestClient(app)


def test_auth_disabled_by_default_is_open(monkeypatch) -> None:
    monkeypatch.delenv("PTAGENT_DOWNSTREAM_AUTH", raising=False)
    client = _client()
    assert client.get("/ptagent/api/health").status_code == 200
    # 开放：无 token 也能访问（未知实验 → 404，而非 401）
    assert client.get("/ptagent/api/experiments/nope").status_code == 404


def test_auth_enabled_requires_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("PTAGENT_DOWNSTREAM_AUTH", "1")
    client = _client()
    # health 永远开放（存活探针）
    assert client.get("/ptagent/api/health").status_code == 200
    # 其他端点无 token → 401（在惰性导入 config 之前就拒绝）
    assert client.get("/ptagent/api/experiments/nope").status_code == 401
    # 非 Bearer 头 → 401
    resp = client.get("/ptagent/api/experiments/nope", headers={"Authorization": "Basic xyz"})
    assert resp.status_code == 401


def test_authenticated_principal_passes_through(monkeypatch) -> None:
    # 覆盖 authorize 模拟"已通过鉴权"，证明端点在鉴权后照常工作
    monkeypatch.setenv("PTAGENT_DOWNSTREAM_AUTH", "1")
    app = FastAPI()
    app.include_router(downstream_router)
    app.dependency_overrides[get_repository] = lambda: InMemoryExperimentRepository()
    app.dependency_overrides[authorize] = lambda: None
    client = TestClient(app)
    assert client.get("/ptagent/api/experiments/nope").status_code == 404  # 过鉴权后照常 404


def test_mutating_request_is_audited(monkeypatch, caplog) -> None:
    monkeypatch.delenv("PTAGENT_DOWNSTREAM_AUTH", raising=False)
    client = _client()
    with caplog.at_level(logging.INFO, logger="ptagent.downstream.audit"):
        client.post("/ptagent/api/experiments", json={"context": {}, "groups": []})
    audited = [r for r in caplog.records if "audit" in r.message and "POST" in r.message]
    assert audited, "mutating request should produce an audit log line"
    assert "principal=anonymous" in audited[0].message


def test_read_request_is_not_audited(monkeypatch, caplog) -> None:
    monkeypatch.delenv("PTAGENT_DOWNSTREAM_AUTH", raising=False)
    client = _client()
    with caplog.at_level(logging.INFO, logger="ptagent.downstream.audit"):
        client.get("/ptagent/api/health")
    assert not [r for r in caplog.records if "audit" in r.message]  # 只读不审计
