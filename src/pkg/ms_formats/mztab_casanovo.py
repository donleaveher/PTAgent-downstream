"""Casanovo mzTab PSM table parsing (identification-style exports)."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any


_REF_INDEX_RE = re.compile(r"index=(\d+)")


def parse_spectra_ref(ref: str) -> int | None:
    """Parse ``ms_run[1]:index=0`` style refs; return 0-based spectrum index."""
    m = _REF_INDEX_RE.search(ref)
    if not m:
        return None
    return int(m.group(1))


def parse_casanovo_mztab_psms(path: Path | str) -> dict[int, dict[str, Any]]:
    """
    Return map ``spectrum_index -> {sequence, score, spectra_ref, aa_scores, proforma}``.

    Column layout matches Casanovo ``ms_io.MztabWriter`` PSH row.
    """
    p = Path(path)
    rows: dict[int, dict[str, Any]] = {}
    with p.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if not row or row[0] != "PSM":
                continue
            if len(row) < 15:
                continue
            sequence = row[1]
            try:
                score = float(row[8])
            except (ValueError, IndexError):
                score = 0.0
            spectra_ref = row[14] if len(row) > 14 else ""
            idx = parse_spectra_ref(spectra_ref)
            if idx is None:
                continue
            aa_scores: list[float] = []
            if len(row) > 19 and row[19] and row[19] != "null":
                for part in row[19].split(","):
                    part = part.strip()
                    if not part:
                        continue
                    try:
                        aa_scores.append(float(part))
                    except ValueError:
                        pass
            proforma = row[20] if len(row) > 20 else ""
            rows[idx] = {
                "sequence": sequence,
                "score": score,
                "spectra_ref": spectra_ref,
                "aa_scores": aa_scores,
                "proforma": proforma,
            }
    return rows


__all__ = ["parse_casanovo_mztab_psms", "parse_spectra_ref"]
