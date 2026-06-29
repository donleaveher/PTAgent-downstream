"""跨实验比较测试（§11.1）：差异蛋白按 accession、疾病按 disease_id 对齐 + API 路由/错误。"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.analysis import compare_experiments
from pkg.experiment import (
    AnnotationTargetType,
    DifferentialDirection,
    DifferentialResult,
    EvidenceLevel,
    ExperimentBundle,
    ExperimentContext,
    ExperimentGroup,
    GroupRole,
    InMemoryExperimentRepository,
    MetaAnnotation,
    ProteinRecord,
)
from router.downstream import downstream_router, get_repository


def _exp(repo, eid, proteins, diff_pids, diseases) -> None:
    """proteins: [(protein_id, accession, gene)]；diff_pids: 差异蛋白的 protein_id 集合；
    diseases: [(gene, disease_id, name)]（CONCLUSION 级）。"""
    repo.save_bundle(
        ExperimentBundle(
            context=ExperimentContext(experiment_id=eid, raw_text="bg"),
            groups=[
                ExperimentGroup(group_id="case", label="Case", role=GroupRole.CASE),
                ExperimentGroup(group_id="ctrl", label="Control", role=GroupRole.CONTROL),
            ],
            proteins=[
                ProteinRecord(protein_id=pid, accession=acc, gene=gene)
                for pid, acc, gene in proteins
            ],
            peptides=[],
        )
    )
    repo.add_differentials(
        [
            DifferentialResult(
                experiment_id=eid,
                protein_id=pid,
                case_group_id="case",
                control_group_id="ctrl",
                log2fc=2.0,
                direction=DifferentialDirection.UP,
                is_differential=(pid in diff_pids),
            )
            for pid, _, _ in proteins
        ]
    )
    repo.add_annotations(
        [
            MetaAnnotation(
                experiment_id=eid,
                target=gene,
                target_type=AnnotationTargetType.GENE,
                attribute=f"disease:{did}",
                value={"disease_id": did, "disease_name": name},
                evidence_level=EvidenceLevel.CONCLUSION,
                source="CTD",
            )
            for gene, did, name in diseases
        ]
    )


def _repo() -> InMemoryExperimentRepository:
    repo = InMemoryExperimentRepository()
    _exp(  # exp_a：差异 P1,P2；结论疾病 D1
        repo, "exp_a",
        [("p1", "P1", "G1"), ("p2", "P2", "G2")],
        {"p1", "p2"},
        [("G1", "D1", "Disease1")],
    )
    _exp(  # exp_b：差异 P2,P3；结论疾病 D1,D2
        repo, "exp_b",
        [("pa", "P2", "G2"), ("pb", "P3", "G3")],
        {"pa", "pb"},
        [("G2", "D1", "Disease1"), ("G3", "D2", "Disease2")],
    )
    return repo


def _client(repo) -> TestClient:
    app = FastAPI()
    app.include_router(downstream_router)
    app.dependency_overrides[get_repository] = lambda: repo
    return TestClient(app)


def test_compare_aligns_on_accession_and_disease() -> None:
    out = compare_experiments(["exp_a", "exp_b"], repository=_repo())
    assert out["experiment_ids"] == ["exp_a", "exp_b"]

    diff = out["differential_proteins"]
    assert diff["shared_in_all"] == ["P2"]  # P2 两实验都差异
    assert diff["by_accession"] == {"P1": ["exp_a"], "P2": ["exp_a", "exp_b"], "P3": ["exp_b"]}

    dis = out["disease_conclusions"]
    assert dis["shared_in_all"] == ["D1"]  # D1 两实验都有结论
    assert dis["by_disease"]["D2"]["experiments"] == ["exp_b"]

    assert out["per_experiment"]["exp_a"] == {"differential_proteins": 2, "disease_conclusions": 1}


def test_service_dedupes_and_rejects_single_id() -> None:
    repo = _repo()
    # 去重后仍是 1 个 → 拒绝
    with pytest.raises(ValueError, match="at least 2"):
        compare_experiments(["exp_a", "exp_a"], repository=repo)


def test_service_unknown_experiment() -> None:
    with pytest.raises(ValueError, match="unknown experiment"):
        compare_experiments(["exp_a", "nope"], repository=_repo())


def test_api_compare_route_not_shadowed_by_path_param() -> None:
    resp = _client(_repo()).get("/ptagent/api/experiments/compare", params={"ids": "exp_a,exp_b"})
    assert resp.status_code == 200, resp.text  # 不被 {experiment_id}=compare 捕获成 404
    assert resp.json()["differential_proteins"]["shared_in_all"] == ["P2"]


def test_api_compare_errors() -> None:
    client = _client(_repo())
    assert client.get("/ptagent/api/experiments/compare", params={"ids": "exp_a"}).status_code == 400
    assert client.get(
        "/ptagent/api/experiments/compare", params={"ids": "exp_a,nope"}
    ).status_code == 404
