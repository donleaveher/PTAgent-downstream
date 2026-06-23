"""本地注释源(TSV 解析 + fetch)单元测试。"""
from __future__ import annotations

from pathlib import Path

from pkg.annotation import MappingAnnotationSource, parse_annotation_tsv

_TSV = (
    "accession\tgo\tec\tinterpro\n"
    "P12345\tGO:0005515;GO:0008270\t2.7.11.1\tIPR000719;IPR011009\n"
    "Q99999\t\t\tIPR000001\n"          # 只有 interpro，其余空
)


def _write(tmp_path: Path) -> Path:
    f = tmp_path / "annot.tsv"
    f.write_text(_TSV, encoding="utf-8")
    return f


def test_parse_annotation_tsv_splits_multivalue(tmp_path: Path) -> None:
    table = parse_annotation_tsv(_write(tmp_path))
    assert set(table) == {"P12345", "Q99999"}
    assert table["P12345"]["go"] == ["GO:0005515", "GO:0008270"]
    assert table["P12345"]["ec"] == ["2.7.11.1"]
    assert table["P12345"]["interpro"] == ["IPR000719", "IPR011009"]
    assert table["Q99999"]["go"] == []                       # 空格元胞 → 空列表
    assert table["Q99999"]["interpro"] == ["IPR000001"]


def test_fetch_returns_only_known(tmp_path: Path) -> None:
    src = MappingAnnotationSource.from_tsv(_write(tmp_path), version="2026_01")
    assert src.version == "2026_01"
    got = src.fetch(["P12345", "NOPE"])
    assert set(got) == {"P12345"}                            # 查不到的不出现
    assert got["P12345"]["ec"] == ["2.7.11.1"]
