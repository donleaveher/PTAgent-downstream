from __future__ import annotations

from pathlib import Path

from pkg.ms_formats import parse_casanovo_mztab_psms


def test_parse_casanovo_mztab_psms(tmp_path: Path) -> None:
    p = tmp_path / "t.mztab"
    p.write_text(
        "\t".join(
            [
                "PSH",
                "sequence",
                "PSM_ID",
                "a",
                "b",
                "c",
                "d",
                "search",
                "search_engine_score[1]",
                "m",
                "rt",
                "ch",
                "em",
                "cm",
                "spectra_ref",
            ]
        )
        + "\n"
        + "\t".join(
            [
                "PSM",
                "PEPTIDE",
                "1",
                "null",
                "null",
                "null",
                "null",
                "[MS, MS:1003281, Casanovo, 1.0]",
                "0.95",
                "null",
                "null",
                "2",
                "450.1",
                "450.0",
                "ms_run[1]:index=0",
                "null",
                "null",
                "null",
                "null",
                "0.1,0.2,0.3",
                "PEPTIDE",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    rows = parse_casanovo_mztab_psms(p)
    assert 0 in rows
    assert rows[0]["sequence"] == "PEPTIDE"
    assert abs(rows[0]["score"] - 0.95) < 1e-6
    assert len(rows[0]["aa_scores"]) == 3
