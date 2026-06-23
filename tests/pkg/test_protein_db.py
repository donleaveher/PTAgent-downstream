"""蛋白库查询(FASTA 精确子串 + I/L 归一)单元测试。"""
from __future__ import annotations

from pathlib import Path

from pkg.protein_db import FastaProteinDB, parse_fasta

_FASTA = (
    ">sp|P12345|TEST_HUMAN Alpha protein OS=Homo sapiens\n"
    "MKWVTFISLLFLFSSAYSRGVFRR\n"
    "PEPTIDEKQQ\n"
    ">tr|Q99999|OTHER_MOUSE Beta\n"
    "AAAAILAAAA\n"
    ">plainid no-bars description here\n"
    "MMMMMM\n"
)


def _write(tmp_path: Path) -> Path:
    f = tmp_path / "db.fasta"
    f.write_text(_FASTA, encoding="utf-8")
    return f


def test_parse_fasta_headers_and_multiline_seq(tmp_path: Path) -> None:
    e = parse_fasta(_write(tmp_path))
    assert set(e) == {"P12345", "Q99999", "plainid"}
    desc, seq = e["P12345"]
    assert desc.startswith("Alpha protein")
    assert seq == "MKWVTFISLLFLFSSAYSRGVFRRPEPTIDEKQQ"      # 多行拼接
    assert e["plainid"][0] == "no-bars description here"     # 非 UniProt 头退化


def test_lookup_substring_hit_and_miss(tmp_path: Path) -> None:
    db = FastaProteinDB.from_fasta(_write(tmp_path), version="2026_01")
    assert db.version == "2026_01"
    hits = db.lookup("PEPTIDEK")
    assert [h["accession"] for h in hits] == ["P12345"]
    assert hits[0]["description"].startswith("Alpha")
    assert db.lookup("WWWWWW") == []                          # 不命中 = novel
    assert db.lookup("") == []


def test_lookup_il_equivalence(tmp_path: Path) -> None:
    # 库里 Q99999 = ...AAILAA...；查 AALLAA（I/L 不可分）默认应命中
    db = FastaProteinDB.from_fasta(_write(tmp_path))
    assert [h["accession"] for h in db.lookup("AALLAA")] == ["Q99999"]
    # 关掉 I/L 归一就不该命中（严格子串）
    strict = FastaProteinDB.from_fasta(_write(tmp_path), il_equiv=False)
    assert strict.lookup("AALLAA") == []
