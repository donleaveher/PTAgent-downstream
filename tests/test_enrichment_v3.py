"""L2 过表达富集：超几何引擎与疾病富集应用服务。"""

from __future__ import annotations

from application.analysis import run_disease_enrichment
from pkg.analysis import over_representation
from pkg.experiment import (
    AnnotationTargetType,
    DifferentialDirection,
    DifferentialResult,
    EvidenceLevel,
    InMemoryExperimentRepository,
    MetaAnnotation,
    ingest_experiment_payload,
)


def test_ora_significant_term() -> None:
    background = {f"G{i}" for i in range(1, 21)}  # 20 个背景基因
    gene_sets = {"D": {"G1", "G2", "G3", "G4", "G5"}}  # 疾病 D 含 5 个
    study = {"G1", "G2", "G3", "G4"}  # 差异集 4 个，全落在 D

    (result,) = over_representation(study, background, gene_sets)
    assert result.overlap == 4
    assert result.term_size == 5
    assert result.study_size == 4 and result.background_size == 20
    assert result.fold_enrichment == 4.0  # (4/4)/(5/20)
    assert result.p_value < 0.01 and result.q_value <= 0.05


def test_ora_clips_study_to_background_and_min_overlap() -> None:
    background = {"G1", "G2", "G3"}
    gene_sets = {"D": {"G1", "G2"}, "E": {"G3"}}
    study = {"G1", "G99"}  # G99 不在背景 → 裁掉，study 实际只剩 G1
    results = over_representation(study, background, gene_sets, min_overlap=2)
    assert results == []  # D 只命中 G1(=1 < min_overlap)，E 命中 0


def _enrichment_payload() -> dict:
    return {
        "context": {"experiment_id": "exp_e", "raw_text": "x"},
        "groups": [{"group_id": "g1", "label": "L1", "role": "case"}],
        "proteins": [
            {"protein_id": f"prot_{i}", "accession": f"P{i}", "gene": f"G{i}", "peptide_ids": []}
            for i in range(1, 6)
        ],
        "peptides": [],
    }


def test_disease_enrichment_service_wires_study_background_and_gene_sets() -> None:
    repo = InMemoryExperimentRepository()
    ingest_experiment_payload(_enrichment_payload(), repo)  # 背景基因 G1..G5

    # CTD 结论：G1/G2/G3 → 疾病 MESH:DX（基因集）
    repo.add_annotations(
        [
            MetaAnnotation(
                experiment_id="exp_e",
                target=g,
                target_type=AnnotationTargetType.GENE,
                attribute="disease:MESH:DX",
                value={"disease_id": "MESH:DX", "disease_name": "Disease X"},
                evidence_level=EvidenceLevel.CONCLUSION,
                source="CTD",
            )
            for g in ("G1", "G2", "G3")
        ]
    )
    # 差异蛋白：prot_1/prot_2（基因 G1/G2）
    repo.add_differentials(
        [
            DifferentialResult(
                experiment_id="exp_e",
                protein_id=pid,
                case_group_id="g1",
                control_group_id="g0",
                log2fc=2.0,
                direction=DifferentialDirection.UP,
                is_differential=True,
            )
            for pid in ("prot_1", "prot_2")
        ]
    )

    summary = run_disease_enrichment("exp_e", repository=repo, min_overlap=1)

    assert summary["background_size"] == 5
    assert summary["study_size"] == 2
    assert summary["terms_tested"] == 1
    term = summary["results"][0]
    assert term["term"] == "MESH:DX"
    assert term["term_name"] == "Disease X"
    assert term["overlap"] == 2  # G1,G2
    assert term["term_size"] == 3  # G1,G2,G3
