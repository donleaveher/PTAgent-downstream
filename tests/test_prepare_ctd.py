"""CTD 预处理脚本：过滤为直接证据精简 CSV + manifest，且产物可被生产 parser 读回。"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from prepare_ctd import filter_ctd_file  # noqa: E402

from pkg.disease.ctd import CTDFileDiseaseSource

_SAMPLE = """# CTD_genes_diseases sample
# Fields: GeneSymbol,GeneID,DiseaseName,DiseaseID,DirectEvidence,InferenceChemicalName,InferenceScore,OmimIDs,PubMedIDs
JAK2,3717,Brain Ischemia,MESH:D002545,marker/mechanism,,,,17522207|19710526
STAT3,6774,Inflammation,MESH:D007249,therapeutic,,,,22899800
CASP3,836,Brain Ischemia,MESH:D002545,,Bisphenol A,12.34,,999
A2M,2,Alzheimer Disease,MESH:D000544,marker/mechanism|therapeutic,,,104300,8696339
"""


def test_filter_keeps_only_direct_and_is_parser_compatible(tmp_path: Path) -> None:
    src = tmp_path / "CTD_genes_diseases.csv"
    src.write_text(_SAMPLE, encoding="utf-8")
    out = tmp_path / "ctd_direct.csv"

    manifest = filter_ctd_file(src, out, version="CTD-2025-09")

    # 只保留 3 条直接证据（CASP3 的化学物推断行被丢弃）
    assert manifest["kept_direct_rows"] == 3
    assert manifest["version"] == "CTD-2025-09"
    assert len(manifest["source_sha256"]) == 64
    assert manifest["source_file"] == "CTD_genes_diseases.csv"

    # manifest 旁车文件如实写出
    sidecar = json.loads(out.with_name(out.name + ".manifest.json").read_text(encoding="utf-8"))
    assert sidecar == manifest

    # 关键验证：精简产物能被生产 parser 直接读回，得到预期直接事实
    source = CTDFileDiseaseSource.from_file(out, version="CTD-2025-09")
    result = source.fetch(["JAK2", "STAT3", "A2M", "CASP3"])
    assert set(result) == {"JAK2", "STAT3", "A2M"}  # CASP3(推断) 不在
    assert result["A2M"][0].evidence_type == "marker/mechanism|therapeutic"
    assert result["JAK2"][0].disease_id == "MESH:D002545"


def test_filter_handles_gzip_input(tmp_path: Path) -> None:
    src = tmp_path / "CTD_genes_diseases.csv.gz"
    with gzip.open(src, "wt", encoding="utf-8") as handle:
        handle.write(_SAMPLE)
    out = tmp_path / "ctd_direct.csv"

    manifest = filter_ctd_file(src, out, version="CTD-gz")

    assert manifest["kept_direct_rows"] == 3
    assert manifest["source_file"] == "CTD_genes_diseases.csv.gz"
    assert CTDFileDiseaseSource.from_file(out).fetch(["Stat3"])  # 大小写归一仍可命中
