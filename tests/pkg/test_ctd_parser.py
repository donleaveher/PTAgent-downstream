"""CTD genes-diseases parser：直接证据保留、推断行排除、跨大小写匹配。"""

from __future__ import annotations

from pkg.disease.ctd import CTDFileDiseaseSource, parse_ctd_genes_diseases

_SAMPLE = [
    "# CTD genes-diseases sample",
    "# Fields: GeneSymbol,GeneID,DiseaseName,DiseaseID,DirectEvidence,InferenceChemicalName,InferenceScore,OmimIDs,PubMedIDs",
    "Jak2,3717,Brain Ischemia,MESH:D002545,marker/mechanism,,,,12345|67890",
    "Stat3,6774,Inflammation,MESH:D007249,therapeutic,,,,222",
    # 间接：DirectEvidence 为空，仅化学物推断 → 必须排除
    "Casp3,836,Brain Ischemia,MESH:D002545,,Sodium Chloride,4.21,,999",
    # 直接证据但类型不在允许列表 → 排除
    "FakeGene,1,Disease X,MESH:D000001,some/other,,,,1",
]


def test_parser_keeps_direct_evidence_only() -> None:
    index = parse_ctd_genes_diseases(_SAMPLE, version="2026_03")
    assert set(index) == {"JAK2", "STAT3"}  # Casp3(推断)、FakeGene(非允许) 已排除
    jak2 = index["JAK2"][0]
    assert jak2.disease_id == "MESH:D002545"
    assert jak2.disease_name == "Brain Ischemia"
    assert jak2.evidence_type == "marker/mechanism"
    assert jak2.pubmed_ids == ("12345", "67890")
    assert jak2.relation_id == "3717|MESH:D002545"
    assert jak2.provenance["db_version"] == "2026_03"


def test_source_matches_genes_case_insensitively() -> None:
    source = CTDFileDiseaseSource(parse_ctd_genes_diseases(_SAMPLE), version="2026_03")
    result = source.fetch(["Jak2", "STAT3", "Unknown"])
    assert set(result) == {"Jak2", "STAT3"}  # 未命中的 Unknown 不出现
    assert result["Jak2"][0].disease_id == "MESH:D002545"
