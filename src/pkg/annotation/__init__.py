"""蛋白注释源包：accession → go/ec/interpro(富集用)。"""
from pkg.annotation.base import AnnotationSource, ProtAnnot
from pkg.annotation.knowledge import ProteinAnnotationFact, ProteinAnnotationSource
from pkg.annotation.local import (
    MappingAnnotationSource,
    get_annotation_source,
    parse_annotation_tsv,
)
from pkg.annotation.uniprot import UniProtAnnotationSource
from pkg.annotation.uniprot_mcp import (
    UniProtMCPAnnotationSource,
    UniProtMCPGeneResolver,
    get_protein_annotation_source,
    parse_uniprot_gene_map,
    parse_uniprot_mcp_result,
)

__all__ = [
    "AnnotationSource",
    "ProtAnnot",
    "ProteinAnnotationFact",
    "ProteinAnnotationSource",
    "MappingAnnotationSource",
    "parse_annotation_tsv",
    "get_annotation_source",
    "UniProtAnnotationSource",
    "UniProtMCPAnnotationSource",
    "UniProtMCPGeneResolver",
    "get_protein_annotation_source",
    "parse_uniprot_gene_map",
    "parse_uniprot_mcp_result",
]
