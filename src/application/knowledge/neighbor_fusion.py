"""Compatibility exports for the renamed neighbor search service."""

from application.knowledge.neighbor_search import (
    generate_fused_neighbor_candidates,
    run_neighbor_search,
)
from pkg.retrieval.providers import (
    StructureEvidenceNeighborProvider,
)

__all__ = [
    "StructureEvidenceNeighborProvider",
    "generate_fused_neighbor_candidates",
    "run_neighbor_search",
]
