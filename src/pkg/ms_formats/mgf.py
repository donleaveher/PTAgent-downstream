"""MGF read/write (centroid peak lists; shared across pipelines, not denovo-specific)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, TextIO


def write_spectrum_block(
    fp: TextIO,
    *,
    precursor_mz: float,
    precursor_charge: int,
    peaks_mz: list[float],
    peaks_intensity: list[float],
    title: str,
    retention_time: float | None = None,
    activation: str | None = None,
    species: str | None = None,
    nce: float | None = None,
    instrument: str | None = None,
) -> None:
    fp.write("BEGIN IONS\n")
    fp.write(f"TITLE={title}\n")
    fp.write(f"PEPMASS={precursor_mz}\n")
    fp.write(f"CHARGE={precursor_charge}+\n")
    if retention_time is not None:
        fp.write(f"RTINSECONDS={retention_time}\n")
    if activation:
        fp.write(f"ACTIVATION={activation}\n")
    meta_parts: list[str] = []
    if species:
        meta_parts.append(f"species={species}")
    if nce is not None:
        meta_parts.append(f"nce={nce}")
    if instrument:
        meta_parts.append(f"instrument={instrument}")
    if meta_parts:
        fp.write(f"COM={' | '.join(meta_parts)}\n")
    for mz, it in zip(peaks_mz, peaks_intensity):
        fp.write(f"{mz} {it}\n")
    fp.write("END IONS\n")


def write_mgf_file(path: Path | str, spectra: list[dict[str, Any]]) -> None:
    """Write multiple spectra to one MGF file (order preserved)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fp:
        for i, spec in enumerate(spectra):
            sid = str(spec.get("spectrum_id") or f"spectrum{i}")
            write_spectrum_block(
                fp,
                precursor_mz=float(spec["precursor_mz"]),
                precursor_charge=int(spec["precursor_charge"]),
                peaks_mz=list(spec["peaks_mz"]),
                peaks_intensity=list(spec["peaks_intensity"]),
                title=sid,
                retention_time=spec.get("retention_time"),
                activation=spec.get("activation"),
                species=spec.get("species"),
                nce=spec.get("nce"),
                instrument=spec.get("instrument"),
            )


def parse_mgf_spectra(path: Path | str) -> list[dict[str, Any]]:
    """
    Parse centroid MGF blocks into dicts with
    ``title``, ``precursor_mz``, ``precursor_charge``, ``peaks_mz``, ``peaks_intensity``.
    """
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"(?i)BEGIN IONS", text)
    out: list[dict[str, Any]] = []
    for raw in blocks:
        raw = raw.strip()
        if not raw or not re.search(r"(?i)END IONS", raw):
            continue
        parts = re.split(r"(?i)END IONS", raw, maxsplit=1)
        body = parts[0]
        title = ""
        pmz: float | None = None
        ch = 1
        pz: list[float] = []
        pi: list[float] = []
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            u = line.upper()
            if u.startswith("TITLE="):
                title = line.split("=", 1)[1].strip()
            elif u.startswith("PEPMASS="):
                m = re.search(r"PEPMASS=([\d.eE+-]+)", line, re.I)
                if m:
                    pmz = float(m.group(1))
            elif u.startswith("CHARGE="):
                m = re.search(r"(\d+)", line)
                if m:
                    ch = int(m.group(1))
            elif re.match(r"^[\d.eE+-]+\s+[\d.eE+-]+$", line):
                a, b = line.split(None, 1)
                pz.append(float(a))
                pi.append(float(b))
        if pmz is None or not pz:
            continue
        out.append(
            {
                "title": title,
                "precursor_mz": pmz,
                "precursor_charge": ch,
                "peaks_mz": pz,
                "peaks_intensity": pi,
            }
        )
    return out


__all__ = ["parse_mgf_spectra", "write_mgf_file", "write_spectrum_block"]
