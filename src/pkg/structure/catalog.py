"""Accession normalization and lightweight structure catalog.

The catalog does not store structure payloads. It records where a structure file
can be found, which accession it represents, and why a query cannot use the
structure channel when no suitable file exists.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

_AF_RE = re.compile(r"AF-(?P<accession>.+?)-F\d+(?:-|\.|$)")
_MODEL_VERSION_RE = re.compile(r"model_v(?P<version>\d+)")
_STRUCT_SUFFIXES = (
    ".cif.gz",
    ".pdb.gz",
    ".mmcif.gz",
    ".mmcif",
    ".cif",
    ".pdb",
    ".gz",
)


class StructureStatus(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    LOW_CONFIDENCE = "low_confidence"


@dataclass(frozen=True)
class NormalizedAccession:
    """Normalized accession while preserving raw and isoform-level identity."""

    raw_accession: str
    accession: str
    isoform_accession: str = ""
    source_form: str = "plain"


@dataclass(frozen=True)
class StructureCatalogRecord:
    """A lightweight pointer to one structure candidate or one missing state."""

    accession: str
    raw_accession: str = ""
    structure_id: str = ""
    source: str = "AlphaFoldDB"
    source_version: str = ""
    format: str = ""
    local_path: str = ""
    object_uri: str = ""
    sha256: str = ""
    taxon_id: int | None = None
    fragment: str = ""
    isoform: str = ""
    mean_plddt: float | None = None
    coverage: float | None = None
    status: StructureStatus = StructureStatus.MISSING
    reason: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def runnable(self) -> bool:
        return self.status is StructureStatus.AVAILABLE and bool(self.local_path)


@runtime_checkable
class StructureCatalog(Protocol):
    def resolve(self, accessions: Iterable[str]) -> dict[str, StructureCatalogRecord]:
        """Return records keyed by the caller's raw accession strings."""

        ...


def normalize_accession(value: str) -> NormalizedAccession:
    """Normalize common UniProt/AlphaFold accession forms to a canonical key.

    Examples:
    ``sp|P40763|STAT3_HUMAN`` -> ``P40763``
    ``P40763-2`` -> ``P40763`` with ``isoform_accession=P40763-2``
    ``AF-P40763-F1-model_v6.cif.gz`` -> ``P40763``
    """

    raw = str(value or "").strip()
    if not raw:
        return NormalizedAccession(raw_accession="", accession="", source_form="empty")

    token = Path(raw).name.strip()
    if "|" in token:
        parts = token.split("|")
        if len(parts) >= 2 and parts[0].lower() in {"sp", "tr", "up"} and parts[1]:
            token = parts[1].strip()
            source_form = "uniprot_pipe"
        else:
            source_form = "plain"
    else:
        source_form = "plain"

    af_match = _AF_RE.search(token)
    if af_match:
        token = af_match.group("accession").strip()
        source_form = "alphafold_model"
    else:
        token = _strip_structure_suffix(token)

    isoform = ""
    if re.fullmatch(r"[A-Za-z0-9]+-\d+", token):
        isoform = token
        token = token.rsplit("-", 1)[0]
        if source_form == "plain":
            source_form = "isoform"

    return NormalizedAccession(
        raw_accession=raw,
        accession=token,
        isoform_accession=isoform,
        source_form=source_form,
    )


def missing_structure_record(
    raw_accession: str,
    *,
    reason: str,
    source_version: str = "",
    source: str = "AlphaFoldDB",
) -> StructureCatalogRecord:
    norm = normalize_accession(raw_accession)
    return StructureCatalogRecord(
        accession=norm.accession,
        raw_accession=raw_accession,
        source=source,
        source_version=source_version,
        isoform=norm.isoform_accession,
        status=StructureStatus.MISSING,
        reason=reason,
        provenance={"normalized_from": norm.raw_accession, "source_form": norm.source_form},
    )


class LocalStructureCatalog:
    """Build a lightweight catalog by scanning a local structure directory."""

    def __init__(
        self,
        structure_dir: str | Path,
        *,
        source: str = "AlphaFoldDB",
        source_version: str = "",
    ) -> None:
        self.structure_dir = Path(structure_dir)
        self.source = source
        self.source_version = source_version
        self._index: dict[str, StructureCatalogRecord] | None = None

    def resolve(self, accessions: Iterable[str]) -> dict[str, StructureCatalogRecord]:
        raw_values = [str(a).strip() for a in accessions if str(a).strip()]
        if not self.structure_dir.exists():
            return {
                raw: missing_structure_record(
                    raw,
                    reason="query_structure_dir_not_found",
                    source=self.source,
                    source_version=self.source_version,
                )
                for raw in raw_values
            }

        index = self._load_index()
        out: dict[str, StructureCatalogRecord] = {}
        for raw in raw_values:
            norm = normalize_accession(raw)
            if not norm.accession:
                out[raw] = missing_structure_record(
                    raw,
                    reason="accession_unresolved",
                    source=self.source,
                    source_version=self.source_version,
                )
                continue
            record = index.get(norm.accession)
            if record is None:
                out[raw] = missing_structure_record(
                    raw,
                    reason="not_found_in_catalog",
                    source=self.source,
                    source_version=self.source_version,
                )
                continue
            out[raw] = StructureCatalogRecord(
                **{
                    **record.__dict__,
                    "raw_accession": raw,
                    "isoform": norm.isoform_accession or record.isoform,
                    "provenance": {
                        **record.provenance,
                        "normalized_from": norm.raw_accession,
                        "source_form": norm.source_form,
                    },
                }
            )
        return out

    def _load_index(self) -> dict[str, StructureCatalogRecord]:
        if self._index is None:
            self._index = _index_structure_dir(
                self.structure_dir,
                source=self.source,
                source_version=self.source_version,
            )
        return self._index


class TsvStructureCatalog:
    """Read structure records from a headered TSV catalog."""

    def __init__(self, catalog_file: str | Path, *, source_version: str = "") -> None:
        self.catalog_file = Path(catalog_file)
        self.source_version = source_version
        self._index: dict[str, StructureCatalogRecord] | None = None

    def resolve(self, accessions: Iterable[str]) -> dict[str, StructureCatalogRecord]:
        raw_values = [str(a).strip() for a in accessions if str(a).strip()]
        if not self.catalog_file.exists():
            return {
                raw: missing_structure_record(
                    raw,
                    reason="structure_catalog_file_not_found",
                    source_version=self.source_version,
                )
                for raw in raw_values
            }

        index = self._load_index()
        out: dict[str, StructureCatalogRecord] = {}
        for raw in raw_values:
            norm = normalize_accession(raw)
            if not norm.accession:
                out[raw] = missing_structure_record(
                    raw, reason="accession_unresolved", source_version=self.source_version
                )
                continue
            record = index.get(norm.accession)
            if record is None:
                out[raw] = missing_structure_record(
                    raw, reason="not_found_in_catalog", source_version=self.source_version
                )
                continue
            out[raw] = StructureCatalogRecord(
                **{
                    **record.__dict__,
                    "raw_accession": raw,
                    "isoform": norm.isoform_accession or record.isoform,
                    "provenance": {
                        **record.provenance,
                        "normalized_from": norm.raw_accession,
                        "source_form": norm.source_form,
                    },
                }
            )
        return out

    def _load_index(self) -> dict[str, StructureCatalogRecord]:
        if self._index is None:
            self._index = _read_tsv_catalog(self.catalog_file, self.source_version)
        return self._index


def build_structure_catalog(cfg) -> StructureCatalog:
    """Build the configured structure catalog.

    If ``structure_catalog_file`` is set, it takes precedence. Otherwise the
    existing query structure directory is scanned lazily.
    """

    from config.paths import project_root

    root = project_root()
    catalog_file_value = str(getattr(cfg, "structure_catalog_file", "") or "").strip()
    if catalog_file_value:
        catalog_file = Path(catalog_file_value)
        if not catalog_file.is_absolute():
            catalog_file = root / catalog_file
        return TsvStructureCatalog(catalog_file, source_version=cfg.version)

    qdir = Path(cfg.query_structure_dir)
    if not qdir.is_absolute():
        qdir = root / qdir
    return LocalStructureCatalog(qdir, source_version=cfg.version)


def _index_structure_dir(
    structure_dir: Path,
    *,
    source: str,
    source_version: str,
) -> dict[str, StructureCatalogRecord]:
    candidates: dict[str, list[Path]] = {}
    for path in structure_dir.iterdir():
        if not path.is_file() or not _looks_like_structure(path.name):
            continue
        norm = normalize_accession(path.name)
        if not norm.accession:
            continue
        candidates.setdefault(norm.accession, []).append(path)

    out: dict[str, StructureCatalogRecord] = {}
    for accession, paths in candidates.items():
        ranked = sorted(paths, key=_path_rank, reverse=True)
        best = ranked[0]
        top_rank = _path_rank(best)
        tied = [p for p in ranked if _path_rank(p) == top_rank]
        if len(tied) > 1:
            out[accession] = StructureCatalogRecord(
                accession=accession,
                structure_id=_structure_id(best.name),
                source=source,
                source_version=source_version,
                format=_structure_format(best.name),
                status=StructureStatus.AMBIGUOUS,
                reason="multiple_equivalent_structure_files",
                provenance={"candidates": [str(p) for p in ranked]},
            )
            continue
        out[accession] = StructureCatalogRecord(
            accession=accession,
            structure_id=_structure_id(best.name),
            source=source,
            source_version=source_version,
            format=_structure_format(best.name),
            local_path=str(best),
            status=StructureStatus.AVAILABLE,
            provenance={"candidates": [str(p) for p in ranked], "candidate_count": len(ranked)},
        )
    return out


def _read_tsv_catalog(path: Path, fallback_version: str) -> dict[str, StructureCatalogRecord]:
    out: dict[str, StructureCatalogRecord] = {}
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            raw_acc = _first(row, "accession", "raw_accession", "structure_id")
            norm = normalize_accession(raw_acc)
            if not norm.accession:
                continue
            status = _parse_status(_first(row, "status") or StructureStatus.AVAILABLE.value)
            source_version = _first(row, "source_version") or fallback_version
            out[norm.accession] = StructureCatalogRecord(
                accession=norm.accession,
                raw_accession=raw_acc,
                structure_id=_first(row, "structure_id") or _structure_id(_first(row, "local_path")),
                source=_first(row, "source") or "AlphaFoldDB",
                source_version=source_version,
                format=_first(row, "format") or _structure_format(_first(row, "local_path")),
                local_path=_first(row, "local_path"),
                object_uri=_first(row, "object_uri"),
                sha256=_first(row, "sha256"),
                taxon_id=_to_int(_first(row, "taxon_id")),
                fragment=_first(row, "fragment"),
                isoform=_first(row, "isoform") or norm.isoform_accession,
                mean_plddt=_to_float_or_none(_first(row, "mean_plddt")),
                coverage=_to_float_or_none(_first(row, "coverage")),
                status=status,
                reason=_first(row, "reason"),
                provenance={"catalog_file": str(path)},
            )
    return out


def _first(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _parse_status(value: str) -> StructureStatus:
    try:
        return StructureStatus(value.strip().lower())
    except ValueError:
        return StructureStatus.MISSING


def _strip_structure_suffix(name: str) -> str:
    for suffix in _STRUCT_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _looks_like_structure(name: str) -> bool:
    return any(name.endswith(suffix) for suffix in _STRUCT_SUFFIXES)


def _structure_id(name: str) -> str:
    return _strip_structure_suffix(Path(name).name)


def _structure_format(name: str) -> str:
    if name.endswith(".cif.gz"):
        return "cif.gz"
    if name.endswith(".pdb.gz"):
        return "pdb.gz"
    if name.endswith(".mmcif.gz"):
        return "mmcif.gz"
    if name.endswith(".mmcif"):
        return "mmcif"
    if name.endswith(".cif"):
        return "cif"
    if name.endswith(".pdb"):
        return "pdb"
    return ""


def _path_rank(path: Path) -> tuple[int, int, int, str]:
    name = path.name
    version = 0
    match = _MODEL_VERSION_RE.search(name)
    if match:
        version = int(match.group("version"))
    preferred_format = {
        "cif.gz": 5,
        "mmcif.gz": 4,
        "pdb.gz": 3,
        "cif": 2,
        "mmcif": 1,
        "pdb": 0,
    }.get(_structure_format(name), -1)
    is_alphafold = 1 if _AF_RE.search(name) else 0
    return (is_alphafold, version, preferred_format, name)


def _to_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float_or_none(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "build_structure_catalog",
    "LocalStructureCatalog",
    "missing_structure_record",
    "NormalizedAccession",
    "normalize_accession",
    "StructureCatalog",
    "StructureCatalogRecord",
    "StructureStatus",
    "TsvStructureCatalog",
]
