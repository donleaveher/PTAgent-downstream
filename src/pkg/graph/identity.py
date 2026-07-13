"""Canonical entity identities for the v2 knowledge graph schema."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping

from pkg.structure import normalize_accession


def canonical_protein_key(accession: str) -> str:
    """Return the canonical primary accession used by ``Protein.key``."""

    normalized = normalize_accession(accession).accession.strip().upper()
    if not normalized:
        raise ValueError("protein accession cannot normalize to an empty key")
    return normalized


def normalize_gene_symbol(symbol: str) -> str:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        raise ValueError("gene symbol cannot normalize to an empty key")
    return normalized


def _meta_gene_id(meta: Mapping[str, Any] | None) -> str:
    if not meta:
        return ""
    for key in ("ncbi_gene_id", "gene_id"):
        value = str(meta.get(key) or "").strip()
        if value:
            return value
    return ""


@dataclass(frozen=True)
class CanonicalGeneIdentity:
    key: str
    symbol: str
    taxon_id: int | None
    ncbi_gene_id: str = ""

    @property
    def properties(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "taxon_id": self.taxon_id,
            "ncbi_gene_id": self.ncbi_gene_id,
        }


def canonical_gene_identity(
    symbol: str,
    *,
    taxon_id: int | None,
    meta: Mapping[str, Any] | None = None,
) -> CanonicalGeneIdentity:
    """Build a species-safe Gene identity, preferring an NCBI Gene ID."""

    normalized_symbol = normalize_gene_symbol(symbol)
    ncbi_gene_id = _meta_gene_id(meta)
    if ncbi_gene_id:
        key = f"NCBIGene:{ncbi_gene_id}"
    elif taxon_id is not None:
        key = f"taxon:{taxon_id}|gene:{normalized_symbol}"
    else:
        key = f"gene:{normalized_symbol}"
    return CanonicalGeneIdentity(
        key=key,
        symbol=normalized_symbol,
        taxon_id=taxon_id,
        ncbi_gene_id=ncbi_gene_id,
    )


def canonical_relation_key(relation_type: str, *identity_parts: object) -> str:
    """Return a stable, namespace-readable relationship identity."""

    canonical = json.dumps(
        [relation_type, *identity_parts],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return f"kgrel_{relation_type.lower()}_{digest}"


__all__ = [
    "CanonicalGeneIdentity",
    "canonical_gene_identity",
    "canonical_protein_key",
    "canonical_relation_key",
    "normalize_gene_symbol",
]
