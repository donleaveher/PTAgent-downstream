"""Foldseek 结构近邻：解析、筛选、provider（含跨物种 大鼠→人 案例）。"""

from __future__ import annotations

from config import StructureSettings
from pkg.structure import (
    CatalogFoldseekRunner,
    FoldseekStructureSearchProvider,
    StaticStructureSearchProvider,
    StructuralNeighbor,
    StructureStatus,
    build_structure_search_provider,
    parse_foldseek_output,
    select_neighbors,
)

# 列序：query target fident qcov tcov prob evalue bits taxid taxname
_SAMPLE_TSV = "\n".join(
    [
        # 自身命中（target == query）→ 应被剔除
        "AF-Q9RAT9-F1-model_v4.cif.gz\tAF-Q9RAT9-F1-model_v4.cif.gz\t1.0\t1.0\t1.0\t1.000\t0.0\t1000\t10116\tRattus norvegicus",
        # 人源近邻（高分）→ 跨物种桥的命中
        "AF-Q9RAT9-F1-model_v4.cif.gz\tAF-P40763-F1-model_v4.cif.gz\t0.42\t0.95\t0.92\t0.98\t1e-30\t320\t9606\tHomo sapiens",
        # 低分鼠源近邻 → 低于 min_score 时被过滤
        "AF-Q9RAT9-F1-model_v4.cif.gz\tAF-LOWHIT-F1-model_v4.cif.gz\t0.20\t0.50\t0.30\t0.40\t1e-3\t80\t10090\tMus musculus",
    ]
)


def test_parse_extracts_accession_and_fields() -> None:
    parsed = parse_foldseek_output(_SAMPLE_TSV.splitlines(), version="afdb-2024_01")
    assert set(parsed) == {"Q9RAT9"}
    neighbors = parsed["Q9RAT9"]
    assert len(neighbors) == 3
    human = next(n for n in neighbors if n.target_accession == "P40763")
    assert human.score == 0.98
    assert human.coverage == 0.92
    assert human.taxon_id == 9606
    assert human.taxon_name == "Homo sapiens"
    assert human.relation_id == "Q9RAT9->P40763"
    assert human.provenance["db_version"] == "afdb-2024_01"


def test_select_excludes_self_filters_and_ranks() -> None:
    parsed = parse_foldseek_output(_SAMPLE_TSV.splitlines())
    selected = select_neighbors(
        parsed["Q9RAT9"], top_k=5, min_score=0.5, min_coverage=0.0, exclude_self=True
    )
    # 自身被剔除、低分(0.40<0.5)被过滤 → 只剩人源近邻
    assert [n.target_accession for n in selected] == ["P40763"]
    assert selected[0].rank == 1


def test_select_top_k_orders_by_score_descending() -> None:
    raw = [
        StructuralNeighbor("Q", "A", score=0.7, coverage=1.0),
        StructuralNeighbor("Q", "B", score=0.9, coverage=1.0),
        StructuralNeighbor("Q", "C", score=0.8, coverage=1.0),
    ]
    selected = select_neighbors(raw, top_k=2)
    assert [(n.target_accession, n.rank) for n in selected] == [("B", 1), ("C", 2)]


class _FakeRunner:
    def __init__(self, tsv: str) -> None:
        self.tsv = tsv
        self.calls: list[list[str]] = []

    def __call__(self, accessions: list[str]) -> str:
        self.calls.append(accessions)
        return self.tsv


def test_provider_cross_species_rat_to_human() -> None:
    runner = _FakeRunner(_SAMPLE_TSV)
    provider = FoldseekStructureSearchProvider(
        runner, version="afdb-2024_01", top_k=10, min_score=0.5, exclude_self=True
    )
    result = provider.search(["Q9RAT9", "Q9RAT9"])  # 去重后只调一次

    assert runner.calls == [["Q9RAT9"]]
    neighbors = result["Q9RAT9"]
    assert len(neighbors) == 1
    top = neighbors[0]
    assert top.target_accession == "P40763"
    assert top.taxon_id == 9606  # 大鼠 query → 人源结构近邻（跨物种桥）
    assert top.rank == 1


def test_provider_normalizes_query_but_preserves_raw_result_key() -> None:
    runner = _FakeRunner(_SAMPLE_TSV)
    provider = FoldseekStructureSearchProvider(
        runner, version="afdb-2024_01", top_k=10, min_score=0.5, exclude_self=True
    )
    raw = "AF-Q9RAT9-F1-model_v4.cif.gz"
    result = provider.search([raw])

    assert runner.calls == [["Q9RAT9"]]
    assert list(result) == [raw]
    assert [n.target_accession for n in result[raw]] == ["P40763"]


def test_provider_empty_input_returns_empty() -> None:
    runner = _FakeRunner(_SAMPLE_TSV)
    provider = FoldseekStructureSearchProvider(runner)
    assert provider.search([]) == {}
    assert runner.calls == []


def test_catalog_foldseek_runner_missing_structure_degrades_without_binary(tmp_path) -> None:
    cfg = StructureSettings(
        query_structure_dir=str(tmp_path / "missing-structures"),
        foldseek_binary="foldseek-not-installed-for-test",
    )
    runner = CatalogFoldseekRunner(cfg)
    provider = FoldseekStructureSearchProvider(runner)

    result = provider.search(["UNKNOWN123"])

    assert result == {"UNKNOWN123": []}
    record = provider.last_structure_records["UNKNOWN123"]
    assert record.status is StructureStatus.MISSING
    assert record.reason == "query_structure_dir_not_found"


def test_provider_switch_defaults_to_foldseek() -> None:
    provider = build_structure_search_provider(StructureSettings())
    assert isinstance(provider, FoldseekStructureSearchProvider)


def test_provider_switch_static_tsv(tmp_path) -> None:
    fixture = tmp_path / "neighbors.tsv"
    fixture.write_text(_SAMPLE_TSV, encoding="utf-8")
    cfg = StructureSettings(
        provider="static",
        static_neighbors_file=str(fixture),
        version="static-dev",
        min_score=0.5,
    )

    provider = build_structure_search_provider(cfg)
    assert isinstance(provider, StaticStructureSearchProvider)

    result = provider.search(["Q9RAT9"])
    assert [n.target_accession for n in result["Q9RAT9"]] == ["P40763"]
    assert result["Q9RAT9"][0].provenance["db_version"] == "static-dev"

    raw = "AF-Q9RAT9-F1-model_v4.cif.gz"
    raw_result = provider.search([raw])
    assert [n.target_accession for n in raw_result[raw]] == ["P40763"]
