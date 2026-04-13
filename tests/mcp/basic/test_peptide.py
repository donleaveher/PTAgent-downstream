"""mcp_tools.basic.peptide（核心 Toolkit，不启 MCP 子进程）。"""

from __future__ import annotations

import pytest

from mcp_tools.basic.peptide import BasicPeptideToolkit


@pytest.fixture
def tk() -> BasicPeptideToolkit:
    return BasicPeptideToolkit()


def test_strip_and_normalize(tk: BasicPeptideToolkit) -> None:
    assert tk.strip_ptm("AM(ox)K") == "AMK"
    assert tk.normalize_ptm_format("AM(ox)K") == "AM[15.99]K"


def test_mass_ordering(tk: BasicPeptideToolkit) -> None:
    mod = tk.calculate_residue_mass_sum("AM[15.99]K")
    bare = tk.calculate_bare_residue_mass_sum("AM[15.99]K")
    assert mod > bare


def test_index_roundtrip(tk: BasicPeptideToolkit) -> None:
    s = "GM[15.99]K"
    assert tk.index_to_peptide(tk.peptide_to_index(s)) == s


def test_normalize_pipeline(tk: BasicPeptideToolkit) -> None:
    out = tk.normalize_peptide_pipeline("AM(ox)K", charge=2)
    assert out["normalized_sequence"] == "AM[15.99]K"
    assert out["token_ids_with_ptm"] == tk.peptide_to_index("AM[15.99]K", strict=True)
    assert out["token_ids_bare"] == tk.peptide_to_index("AMK", strict=True)
    assert out["mass_da"]["residue_sum"] > 0
    assert out["mz"] > 0

    back = tk.token_ids_to_canonical_peptides(out["token_ids_with_ptm"])
    assert back["peptide_with_ptm"] == "AM[15.99]K"
    assert back["peptide_bare"] == "AMK"
    assert back["token_ids_bare"] == out["token_ids_bare"]

    mass = tk.peptide_mass_and_mz(out["token_ids_with_ptm"], charge=2)
    assert mass["normalized_sequence"] == out["normalized_sequence"]
    assert mass["token_ids_with_ptm"] == out["token_ids_with_ptm"]
    assert mass["residue_sum_da"] == out["mass_da"]["residue_sum"]
    assert mass["neutral_mass_da"] == out["mass_da"]["neutral_peptide"]
    assert mass["mz"] == out["mz"]
    assert mass["charge"] == 2
