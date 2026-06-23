"""蛋白库查询包：肽 → 含此肽的蛋白(查库归属用)。"""
from pkg.protein_db.base import ProteinDB, ProteinHit
from pkg.protein_db.fasta import FastaProteinDB, get_protein_db, parse_fasta

__all__ = [
    "ProteinDB",
    "ProteinHit",
    "FastaProteinDB",
    "parse_fasta",
    "get_protein_db",
]
