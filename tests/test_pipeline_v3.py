"""§11.2 下游管线编排端到端测试（全程假源，离线）。

串起：base_annotation → ctd_disease → differential → enrichment → hypothesis
→ kg_projection → deep_search → freeze → report，并覆盖幂等重跑、失败隔离、
子集执行、状态查询。
"""
from __future__ import annotations

from application.orchestration import (
    DownstreamPipelineConfig,
    StepStatus,
    pipeline_status,
    run_downstream_pipeline,
)
from pkg.annotation import ProteinAnnotationFact
from pkg.deep_search import EvidenceRecord, EvidenceStance, InMemoryLiteratureSource
from pkg.disease import GeneDiseaseFact, InMemoryGeneResolver
from pkg.experiment import (
    EvidenceLevel,
    ExperimentBundle,
    ExperimentContext,
    ExperimentGroup,
    GroupRole,
    InMemoryExperimentRepository,
    ProteinQuantification,
    ProteinRecord,
)
from pkg.graph import InMemoryGraphStore
from pkg.structure import StructuralNeighbor

EXP = "exp_pipe"


class _FakeAnnot:
    name = "UniProt-MCP"
    version = "2026_03"

    def fetch(self, accessions: list[str]) -> dict[str, list[ProteinAnnotationFact]]:
        return {
            "P1": [
                ProteinAnnotationFact(
                    accession="P1", attribute="domain", value="JAK",
                    provenance={"db_version": self.version},
                )
            ]
        }


class _FakeCTD:
    name = "CTD"
    version = "2026_03"

    def fetch(self, genes: list[str]) -> dict[str, list[GeneDiseaseFact]]:
        table = {
            "Jak2": [GeneDiseaseFact("Jak2", "MESH:D002545", "Brain Ischemia", "marker/mechanism")],
            "HUMANG": [GeneDiseaseFact("HUMANG", "MESH:D007249", "Inflammation", "therapeutic")],
        }
        return {g: table[g] for g in genes if g in table}


class _FakeStructure:
    name = "Foldseek-AlphaFold"
    version = "afdb-2024_01"

    def search(self, accessions: list[str], *, top_k: int | None = None):
        mapping = {
            "Q_NOVEL": [StructuralNeighbor("Q_NOVEL", "P_HUMAN", score=0.93, coverage=0.9, taxon_id=9606)]
        }
        return {acc: mapping.get(acc, []) for acc in accessions}


def _quants(protein_id: str, case_hi: float, ctrl_lo: float) -> list[ProteinQuantification]:
    rows = []
    for i in (1, 2):
        rows.append(ProteinQuantification(
            experiment_id=EXP, protein_id=protein_id, group_id="g_case",
            sample_id=f"c{i}", abundance=case_hi + i,
        ))
        rows.append(ProteinQuantification(
            experiment_id=EXP, protein_id=protein_id, group_id="g_ctrl",
            sample_id=f"k{i}", abundance=ctrl_lo + i,
        ))
    return rows


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
                ProteinRecord(protein_id="prot1", accession="P1", gene="Jak2", taxon_id=10116),
                ProteinRecord(protein_id="prot2", accession="Q_NOVEL", gene="Novelx", taxon_id=10116),
            ],
            peptides=[],
        )
    )
    repo.add_quantifications(_quants("prot1", 100, 10) + _quants("prot2", 80, 8))
    return repo


def _full_config(**overrides) -> DownstreamPipelineConfig:
    ctd = _FakeCTD()
    cfg = DownstreamPipelineConfig(
        snapshot_version="1.0",
        pipeline_version="test-pipe",
        enrichment_min_overlap=1,
        annotation_source=_FakeAnnot(),
        disease_source=ctd,
        structure_provider=_FakeStructure(),
        gene_resolver=InMemoryGeneResolver({"P_HUMAN": "HUMANG"}),
        literature_source=InMemoryLiteratureSource(
            by_disease={"MESH:D007249": [EvidenceRecord(EvidenceStance.SUPPORT, "t", "PMID:1", "lit")]}
        ),
        graph_store=InMemoryGraphStore(),
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def test_full_pipeline_runs_end_to_end() -> None:
    repo = _seed()
    result = run_downstream_pipeline(EXP, repository=repo, config=_full_config())

    assert result.completed is True
    assert result.failed_step is None
    statuses = result.step_statuses()
    assert statuses["import"] == "skipped"  # 已预先导入
    for step in ("base_annotation", "ctd_disease", "differential", "enrichment",
                 "hypothesis", "kg_projection", "deep_search", "freeze", "report"):
        assert statuses[step] == "ok", f"{step} not ok: {statuses}"

    # 报告产出 + 快照落库
    assert result.report is not None
    assert len(result.report.sections) == 8
    assert result.snapshot_version == "1.0"
    assert [s.snapshot_version for s in repo.list_snapshots(EXP)] == ["1.0"]

    # 链路产物都在库里：结论(Jak2→缺血) + 假说升结论(prot2→炎症) + 差异 + 富集 + 历史
    status = pipeline_status(EXP, repository=repo)
    assert status["conclusions"] >= 1
    assert status["differentials"] == 2
    assert status["enrichments"] >= 1
    assert status["annotation_history"] >= 1
    assert status["snapshots"] == ["1.0"]


def test_pipeline_rerun_is_idempotent() -> None:
    repo = _seed()
    cfg = _full_config()
    run_downstream_pipeline(EXP, repository=repo, config=cfg)
    second = run_downstream_pipeline(EXP, repository=repo, config=cfg)

    assert second.completed is True
    assert second.step_statuses()["freeze"] == "skipped"  # 版本已冻结 → 跳过
    assert second.report is not None
    assert [s.snapshot_version for s in repo.list_snapshots(EXP)] == ["1.0"]  # 不重复冻结


def test_failure_is_isolated_and_stops_chain() -> None:
    repo = _seed()
    cfg = _full_config(literature_source=None)  # deep_search 无源 → 该步报错
    result = run_downstream_pipeline(EXP, repository=repo, config=cfg)

    assert result.completed is False
    assert result.failed_step == "deep_search"
    statuses = result.step_statuses()
    assert statuses["deep_search"] == "failed"
    # 失败后中止：freeze/report 未执行
    assert "freeze" not in statuses and "report" not in statuses
    assert repo.list_snapshots(EXP) == []


def test_pipeline_runs_step_subset() -> None:
    repo = _seed()
    result = run_downstream_pipeline(
        EXP, repository=repo, config=_full_config(),
        steps=["base_annotation", "ctd_disease"],
    )
    assert [s.name for s in result.steps] == ["base_annotation", "ctd_disease"]
    assert result.completed is True
    assert repo.list_snapshots(EXP) == []  # 没跑到 freeze


def test_import_step_ingests_bundle() -> None:
    repo = InMemoryExperimentRepository()
    bundle = ExperimentBundle(
        context=ExperimentContext(experiment_id=EXP, raw_text="x"),
        groups=[ExperimentGroup(group_id="g_case", label="Case", role=GroupRole.CASE)],
        proteins=[ProteinRecord(protein_id="prot1", accession="P1", gene="Jak2")],
        peptides=[],
    )
    result = run_downstream_pipeline(
        EXP, repository=repo,
        config=DownstreamPipelineConfig(bundle=bundle),
        steps=["import"],
    )
    assert result.step_statuses()["import"] == "ok"
    assert repo.get_context(EXP) is not None  # 已导入


def test_unknown_experiment_and_unknown_step_raise() -> None:
    import pytest

    repo = _seed()
    with pytest.raises(ValueError):
        run_downstream_pipeline("nope", repository=repo, config=_full_config())
    with pytest.raises(ValueError):
        run_downstream_pipeline(EXP, repository=repo, config=_full_config(), steps=["bogus"])


def _repo_prot2(case_hi: float, ctrl_lo: float) -> InMemoryExperimentRepository:
    """只含 prot2(Q_NOVEL，有结构近邻)；是否差异由丰度决定。"""
    repo = InMemoryExperimentRepository()
    repo.save_bundle(ExperimentBundle(
        context=ExperimentContext(experiment_id=EXP, raw_text="ischemia", organism="rat"),
        groups=[
            ExperimentGroup(group_id="g_case", label="Case", role=GroupRole.CASE),
            ExperimentGroup(group_id="g_ctrl", label="Control", role=GroupRole.CONTROL),
        ],
        proteins=[ProteinRecord(protein_id="prot2", accession="Q_NOVEL", gene="Novelx", taxon_id=10116)],
        peptides=[],
    ))
    repo.add_quantifications(_quants("prot2", case_hi, ctrl_lo))
    return repo


def test_hypotheses_restricted_to_differential_proteins() -> None:
    """Q2：非差异蛋白即便有结构近邻也不出假说；关掉开关退回全蛋白；差异蛋白照常出。"""
    steps = ["differential", "hypothesis"]

    # 非差异（case≈control）+ restrict 默认开 → 0 假说
    repo_flat = _repo_prot2(10, 10)
    run_downstream_pipeline(EXP, repository=repo_flat, config=_full_config(), steps=steps)
    assert all(not d.is_differential for d in repo_flat.list_differentials(EXP))
    assert pipeline_status(EXP, repository=repo_flat)["hypotheses"] == 0

    # 同样非差异，但关掉 restrict → 退回全蛋白 → 出假说（证明是过滤所致，非结构源缺失）
    repo_off = _repo_prot2(10, 10)
    run_downstream_pipeline(
        EXP, repository=repo_off, config=_full_config(restrict_to_differential=False), steps=steps
    )
    assert pipeline_status(EXP, repository=repo_off)["hypotheses"] >= 1

    # 差异（case≫control）+ restrict 默认开 → 在差异集 → 出假说（证明不过度过滤）
    repo_diff = _repo_prot2(100, 10)
    run_downstream_pipeline(EXP, repository=repo_diff, config=_full_config(), steps=steps)
    assert any(d.is_differential for d in repo_diff.list_differentials(EXP))
    assert pipeline_status(EXP, repository=repo_diff)["hypotheses"] >= 1
