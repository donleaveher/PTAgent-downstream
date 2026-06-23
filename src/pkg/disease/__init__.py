"""基因-疾病关联领域包：CTD 直接证据 → 基因级结论。"""

from pkg.disease.ctd import (
    CTDFileDiseaseSource,
    get_disease_source,
    iter_direct_evidence_rows,
    parse_ctd_genes_diseases,
)
from pkg.disease.gene_resolver import GeneResolver, InMemoryGeneResolver, get_gene_resolver
from pkg.disease.types import GeneDiseaseFact, GeneDiseaseSource

__all__ = [
    "CTDFileDiseaseSource",
    "GeneDiseaseFact",
    "GeneDiseaseSource",
    "GeneResolver",
    "InMemoryGeneResolver",
    "get_disease_source",
    "get_gene_resolver",
    "iter_direct_evidence_rows",
    "parse_ctd_genes_diseases",
]
