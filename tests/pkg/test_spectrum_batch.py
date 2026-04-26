from __future__ import annotations

from pathlib import Path

import pytest

from pkg.ms_formats import client_item_to_canonical, write_mgf_file


def test_client_item_species_nce_instrument() -> None:
    item = {
        "spectrum": [{"mz": 100.0, "intensity": 1.0}],
        "precursorMz": 500.0,
        "precursorCharge": 2,
        "Name": "s1",
        "species": "Homo sapiens",
        "NCE": 27.5,
        "instrument": "QE",
        "actType": "HCD",
    }
    out = client_item_to_canonical(item, 0)
    assert out["species"] == "Homo sapiens"
    assert out["nce"] == 27.5
    assert out["instrument"] == "QE"
    assert out["activation"] == "HCD"


def test_write_mgf_includes_com_meta(tmp_path: Path) -> None:
    spec = {
        "spectrum_id": "a",
        "precursor_mz": 400.0,
        "precursor_charge": 1,
        "peaks_mz": [100.0],
        "peaks_intensity": [1.0],
        "species": "mouse",
        "nce": 30.0,
    }
    p = tmp_path / "o.mgf"
    write_mgf_file(p, [spec])
    text = p.read_text(encoding="utf-8")
    assert "COM=" in text
    assert "species=mouse" in text
    assert "nce=30.0" in text


def test_write_mzml_roundtrip_smoke(tmp_path: Path) -> None:
    pytest.importorskip("psims")
    from pkg.ms_formats import write_mzml_ms2_file

    spec = {
        "spectrum_id": "scan=1",
        "precursor_mz": 400.0,
        "precursor_charge": 1,
        "peaks_mz": [100.0, 200.0],
        "peaks_intensity": [1.0, 2.0],
        "activation": "HCD",
    }
    out = tmp_path / "t.mzml"
    write_mzml_ms2_file(out, [spec])
    assert out.is_file()
    assert b"mzML" in out.read_bytes()[:200]
