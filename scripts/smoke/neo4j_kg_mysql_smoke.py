"""Real MySQL-to-Neo4j knowledge-graph integration smoke test.

This test creates two isolated MySQL experiments, projects both through the
production ``Neo4jGraphStore``, and verifies:

    MySQL facts -> Neo4j constraints/nodes/edges -> graph traversal
    -> idempotent re-projection -> target workspace cleanup -> peer isolation

It deliberately leaves general graph facts in Neo4j because they model the
shared knowledge layer. By default it removes both disposable *experiment*
workspaces; use ``--keep-peer-workspace`` only when inspecting the peer graph
in Neo4j Browser after the run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
_EXPERIMENT_ID_MAX_LENGTH = 64
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - local setup issue only
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(PROJECT_ROOT / ".env", override=False)

os.environ.setdefault("PTAGENT_JWT__SECRET_KEY", "dev")
os.environ.setdefault("PTAGENT_EXPERIMENT_DATABASE__HOST", "127.0.0.1")
os.environ.setdefault("PTAGENT_EXPERIMENT_DATABASE__PORT", "3307")
os.environ.setdefault("PTAGENT_EXPERIMENT_DATABASE__USER", "ptagent")
os.environ.setdefault("PTAGENT_EXPERIMENT_DATABASE__PASSWORD", "ptagent_change_me")
os.environ.setdefault("PTAGENT_EXPERIMENT_DATABASE__DATABASE", "ptagent_experiment")

from application.graph.project_kg import project_experiment_kg  # noqa: E402
from config.graph_settings import get_graph_settings  # noqa: E402
from pkg.experiment import (  # noqa: E402
    AnnotationTargetType,
    DifferentialDirection,
    DifferentialResult,
    EvidenceLevel,
    ExperimentBundle,
    ExperimentContext,
    ExperimentGroup,
    FusedCandidate,
    GroupRole,
    MetaAnnotation,
    MySQLExperimentStore,
    NeighborEvidence,
    NeighborEvidenceStatus,
    NeighborSearchRun,
    ProteinRecord,
    StructureNeighborEvidence,
    StructureSearchRun,
)
from pkg.graph import (  # noqa: E402
    EdgeType,
    GraphScope,
    Neo4jGraphStore,
    NodeLabel,
    NodeRef,
    canonical_gene_identity,
    canonical_protein_key,
    normalize_gene_symbol,
)


@dataclass(frozen=True)
class SmokeExperiment:
    experiment_id: str
    token: str
    gene_accession: str
    hypothesis_accession: str
    gene: str
    conclusion_disease_id: str
    hypothesis_disease_id: str
    structure_target_accession: str
    fused_target_accession: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--experiment-id",
        default="",
        help="Optional fixed primary experiment ID; a peer ID is derived from it.",
    )
    parser.add_argument(
        "--keep-peer-workspace",
        action="store_true",
        help="Keep the peer experiment workspace for inspection after isolation checks.",
    )
    return parser.parse_args()


def _new_experiment_id() -> str:
    return "exp_neo4j_smoke_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _make_seed(experiment_id: str, *, token: str) -> SmokeExperiment:
    return SmokeExperiment(
        experiment_id=experiment_id,
        token=token,
        gene_accession=f"NEOSMOKE_GENE_{token}",
        hypothesis_accession=f"NEOSMOKE_HYP_{token}",
        gene=f"NeoSmokeGene{token}",
        conclusion_disease_id=f"SMOKE:{token}:CONCLUSION",
        hypothesis_disease_id=f"SMOKE:{token}:HYPOTHESIS",
        structure_target_accession=f"NEOSMOKE_NEIGHBOR_{token}",
        fused_target_accession=f"NEOSMOKE_NEIGHBOR_{token}",
    )


def _unique_token(experiment_id: str, role: str) -> str:
    digest = hashlib.sha256(experiment_id.encode("utf-8")).hexdigest()[:12]
    return f"{role}_{digest}"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def _seed_experiment(store: MySQLExperimentStore, seed: SmokeExperiment) -> None:
    exp_id = seed.experiment_id
    gene_protein_id = f"{exp_id}:protein:gene"
    hypothesis_protein_id = f"{exp_id}:protein:hypothesis"
    store.save_bundle(
        ExperimentBundle(
            context=ExperimentContext(
                experiment_id=exp_id,
                session_id="neo4j_kg_smoke",
                title="Neo4j KG integration smoke test",
                raw_text="Validate MySQL-to-Neo4j graph projection and isolation.",
                disease=["Neo4j smoke fixture"],
                organism="Homo sapiens",
                taxon_id=9606,
                assay="fixture",
            ),
            groups=[
                ExperimentGroup(group_id="case", label="Case", role=GroupRole.CASE),
                ExperimentGroup(
                    group_id="control", label="Control", role=GroupRole.CONTROL
                ),
            ],
            proteins=[
                ProteinRecord(
                    protein_id=gene_protein_id,
                    accession=seed.gene_accession,
                    gene=seed.gene,
                    organism="Homo sapiens",
                    taxon_id=9606,
                ),
                ProteinRecord(
                    protein_id=hypothesis_protein_id,
                    accession=seed.hypothesis_accession,
                    gene=f"{seed.gene}Neighbor",
                    organism="Homo sapiens",
                    taxon_id=9606,
                ),
            ],
            peptides=[],
        )
    )
    store.add_annotations(
        [
            MetaAnnotation(
                annotation_id=f"ann_{seed.token}_conclusion",
                experiment_id=exp_id,
                target=seed.gene,
                target_type=AnnotationTargetType.GENE,
                attribute=f"disease:{seed.conclusion_disease_id}",
                value={
                    "disease_id": seed.conclusion_disease_id,
                    "disease_name": f"Neo4j conclusion disease {seed.token}",
                },
                evidence_level=EvidenceLevel.CONCLUSION,
                source="neo4j-smoke-fixture",
            ),
            MetaAnnotation(
                annotation_id=f"ann_{seed.token}_hypothesis",
                experiment_id=exp_id,
                target=hypothesis_protein_id,
                target_type=AnnotationTargetType.PROTEIN,
                attribute=f"disease:{seed.hypothesis_disease_id}",
                value={
                    "disease_id": seed.hypothesis_disease_id,
                    "disease_name": f"Neo4j hypothesis disease {seed.token}",
                },
                evidence_level=EvidenceLevel.HYPOTHESIS,
                source="neo4j-smoke-fixture",
            ),
        ]
    )
    store.add_differentials(
        [
            DifferentialResult(
                experiment_id=exp_id,
                protein_id=gene_protein_id,
                case_group_id="case",
                control_group_id="control",
                log2fc=2.0,
                direction=DifferentialDirection.UP,
                is_differential=True,
            ),
            DifferentialResult(
                experiment_id=exp_id,
                protein_id=hypothesis_protein_id,
                case_group_id="case",
                control_group_id="control",
                log2fc=-1.5,
                direction=DifferentialDirection.DOWN,
                is_differential=True,
            ),
        ]
    )
    run_id = f"strun_{seed.token}"
    store.save_structure_search_run(
        StructureSearchRun(
            run_id=run_id,
            experiment_id=exp_id,
            provider="neo4j-smoke-fixture",
            provider_version="1",
            db_version="fixture",
            params_hash="a" * 64,
            params={"top_k": 1},
            status="completed",
            meta={"neighbor_count": 1},
        )
    )
    store.add_structure_neighbor_evidence(
        [
            StructureNeighborEvidence(
                evidence_id=f"sne_{seed.token}",
                run_id=run_id,
                experiment_id=exp_id,
                query_protein_id=hypothesis_protein_id,
                query_accession=seed.hypothesis_accession,
                target_accession=seed.structure_target_accession,
                score=0.95,
                coverage=0.8,
                rank=1,
                taxon_id=9606,
                relation_id=(
                    f"{seed.hypothesis_accession}->{seed.structure_target_accession}"
                ),
            )
        ]
    )
    sequence_run_id = f"nrun_sequence_{seed.token}"
    store.save_neighbor_search_run(
        NeighborSearchRun(
            run_id=sequence_run_id,
            experiment_id=exp_id,
            provider_id="sequence.kmer",
            provider="Sequence-Kmer",
            provider_version="fixture-1",
            channel="sequence",
            db_version="fixture",
            params_hash="b" * 64,
            params={"k_kmer": 3, "top_k": 1},
            status="completed",
            meta={"candidate_count": 1},
        )
    )
    store.add_neighbor_evidence(
        [
            NeighborEvidence(
                evidence_id=f"seq_{seed.token}",
                run_id=sequence_run_id,
                experiment_id=exp_id,
                query_protein_id=hypothesis_protein_id,
                query_accession=seed.hypothesis_accession,
                target_type="protein",
                target_id=seed.fused_target_accession,
                relation_type="SEQUENCE_NEIGHBOR",
                channel="sequence",
                provider="Sequence-Kmer",
                provider_version="fixture-1",
                rank=1,
                score=0.88,
                meta={"k_kmer": 3},
            )
        ]
    )
    store.add_neighbor_statuses(
        [
            NeighborEvidenceStatus(
                status_id=f"nes_sequence_{seed.token}",
                run_id=sequence_run_id,
                experiment_id=exp_id,
                query_protein_id=hypothesis_protein_id,
                query_accession=seed.hypothesis_accession,
                channel="sequence",
                provider="Sequence-Kmer",
                provider_version="fixture-1",
                status="completed",
                meta={"candidate_count": 1},
            )
        ]
    )
    store.add_fused_candidates(
        [
            FusedCandidate(
                candidate_id=f"fc_{seed.token}",
                experiment_id=exp_id,
                query_protein_id=hypothesis_protein_id,
                query_accession=seed.hypothesis_accession,
                target_type="protein",
                target_id=seed.fused_target_accession,
                relation_type="CANDIDATE_NEIGHBOR",
                fused_score=0.87,
                fusion_rank=1,
                support_channels=["structure", "sequence"],
                evidence_ids=[f"sne_{seed.token}", f"seq_{seed.token}"],
            )
        ]
    )


def _assert_projection(
    graph: Neo4jGraphStore, seed: SmokeExperiment, summary: dict[str, object]
) -> None:
    exp_id = seed.experiment_id
    _require(summary.get("structural_neighbors") == 1, "missing structural graph edge")
    _require(summary.get("candidate_neighbors") == 1, "missing fused candidate graph edge")
    _require(
        graph.count_nodes(scope=GraphScope.EXPERIMENT, experiment_id=exp_id) == 3,
        "expected two group nodes and one comparison node",
    )
    _require(
        graph.count_edges(scope=GraphScope.EXPERIMENT, experiment_id=exp_id) == 6,
        "expected hypothesis, candidate, comparison links, and differential edges",
    )

    conclusion_links = graph.protein_diseases(
        seed.gene_accession, experiment_id=exp_id
    )
    _require(
        any(
            link.disease_key == seed.conclusion_disease_id
            and link.evidence_level == EvidenceLevel.CONCLUSION.value
            and link.via == f"gene:{normalize_gene_symbol(seed.gene)}"
            for link in conclusion_links
        ),
        "gene conclusion is not traversable through ENCODED_BY",
    )
    hypothesis_links = graph.protein_diseases(
        seed.hypothesis_accession, experiment_id=exp_id
    )
    _require(
        any(
            link.disease_key == seed.hypothesis_disease_id
            and link.evidence_level == EvidenceLevel.HYPOTHESIS.value
            and link.via == "protein"
            for link in hypothesis_links
        ),
        "experiment-scoped protein hypothesis is not traversable",
    )
    structure_edges = graph.neighbors(
        NodeRef(NodeLabel.PROTEIN, canonical_protein_key(seed.hypothesis_accession)),
        EdgeType.STRUCTURAL_NEIGHBOR,
    )
    _require(
        any(
            edge.end.key == canonical_protein_key(seed.structure_target_accession)
            for edge in structure_edges
        ),
        "structural neighbor is missing from Neo4j",
    )
    candidate_edges = graph.neighbors(
        NodeRef(NodeLabel.PROTEIN, canonical_protein_key(seed.hypothesis_accession)),
        EdgeType.CANDIDATE_NEIGHBOR,
        experiment_id=exp_id,
    )
    _require(
        any(
            edge.end.key == canonical_protein_key(seed.fused_target_accession)
            for edge in candidate_edges
        ),
        "fused candidate neighbor is missing from Neo4j",
    )


def _assert_fusion_evidence_alignment(
    repository: MySQLExperimentStore, seed: SmokeExperiment
) -> None:
    sequence_evidence = [
        row
        for row in repository.list_neighbor_evidence(seed.experiment_id)
        if row.evidence_id == f"seq_{seed.token}"
    ]
    _require(
        len(sequence_evidence) == 1
        and sequence_evidence[0].channel == "sequence"
        and sequence_evidence[0].target_id == seed.fused_target_accession,
        "fused candidate does not have matching sequence neighbor evidence",
    )
    candidate = next(
        (
            row
            for row in repository.list_fused_candidates(seed.experiment_id)
            if row.candidate_id == f"fc_{seed.token}"
        ),
        None,
    )
    _require(candidate is not None, "expected fused candidate was not persisted")
    _require(
        set(candidate.support_channels) == {"structure", "sequence"}
        and set(candidate.evidence_ids) == {f"sne_{seed.token}", f"seq_{seed.token}"}
        and candidate.target_id == seed.fused_target_accession,
        "fused candidate provenance does not match its structure and sequence evidence",
    )


def _node_state(
    graph: Neo4jGraphStore, label: NodeLabel, key: str
) -> dict[str, object] | None:
    node = graph.get_node(label, key)
    if node is None:
        return None
    return {
        "label": node.label.value,
        "key": node.key,
        "scope": node.scope.value,
        "experiment_id": node.experiment_id,
        "properties": node.properties,
        "mysql_ref": node.mysql_ref,
    }


def _edge_states(
    graph: Neo4jGraphStore,
    seed: SmokeExperiment,
    edge_type: EdgeType,
) -> list[dict[str, object]]:
    return [
        {
            "key": edge.key,
            "type": edge.type.value,
            "scope": edge.scope.value,
            "experiment_id": edge.experiment_id,
            "from": edge.start.key,
            "to": edge.end.key,
            "properties": edge.properties,
        }
        for edge in graph.neighbors(
            NodeRef(
                NodeLabel.PROTEIN,
                canonical_protein_key(seed.hypothesis_accession),
            ),
            edge_type,
            experiment_id=(
                seed.experiment_id
                if edge_type is EdgeType.CANDIDATE_NEIGHBOR
                else None
            ),
        )
    ]


def _kg_state(graph: Neo4jGraphStore, seed: SmokeExperiment) -> dict[str, object]:
    exp_id = seed.experiment_id
    return {
        "experiment_id": exp_id,
        "workspace_counts": {
            "nodes": graph.count_nodes(scope=GraphScope.EXPERIMENT, experiment_id=exp_id),
            "edges": graph.count_edges(scope=GraphScope.EXPERIMENT, experiment_id=exp_id),
        },
        "key_nodes": [
            _node_state(
                graph, NodeLabel.PROTEIN, canonical_protein_key(seed.gene_accession)
            ),
            _node_state(
                graph,
                NodeLabel.PROTEIN,
                canonical_protein_key(seed.hypothesis_accession),
            ),
            _node_state(
                graph,
                NodeLabel.GENE,
                canonical_gene_identity(seed.gene, taxon_id=9606).key,
            ),
            _node_state(graph, NodeLabel.DISEASE, seed.conclusion_disease_id),
            _node_state(graph, NodeLabel.DISEASE, seed.hypothesis_disease_id),
            _node_state(graph, NodeLabel.GROUP, f"{exp_id}:case"),
            _node_state(graph, NodeLabel.GROUP, f"{exp_id}:control"),
        ],
        "disease_traversals": {
            seed.gene_accession: [
                {
                    "disease_id": link.disease_key,
                    "disease_name": link.disease_name,
                    "evidence_level": link.evidence_level,
                    "via": link.via,
                    "edge_key": link.edge_key,
                }
                for link in graph.protein_diseases(
                    seed.gene_accession, experiment_id=exp_id
                )
            ],
            seed.hypothesis_accession: [
                {
                    "disease_id": link.disease_key,
                    "disease_name": link.disease_name,
                    "evidence_level": link.evidence_level,
                    "via": link.via,
                    "edge_key": link.edge_key,
                }
                for link in graph.protein_diseases(
                    seed.hypothesis_accession, experiment_id=exp_id
                )
            ],
        },
        "structural_neighbors": _edge_states(
            graph, seed, EdgeType.STRUCTURAL_NEIGHBOR
        ),
        "candidate_neighbors": _edge_states(
            graph, seed, EdgeType.CANDIDATE_NEIGHBOR
        ),
    }


def _structure_state(
    repository: MySQLExperimentStore, seed: SmokeExperiment
) -> dict[str, object]:
    return {
        "experiment_id": seed.experiment_id,
        "search_runs": [
            row.model_dump(mode="json")
            for row in repository.list_structure_search_runs(seed.experiment_id)
        ],
        "neighbor_evidence": [
            row.model_dump(mode="json")
            for row in repository.list_structure_neighbor_evidence(seed.experiment_id)
        ],
        "catalog_statuses": [
            row.model_dump(mode="json")
            for row in repository.list_structure_statuses(seed.experiment_id)
        ],
        "sequence_search_runs": [
            row.model_dump(mode="json")
            for row in repository.list_neighbor_search_runs(seed.experiment_id)
            if row.channel == "sequence"
        ],
        "sequence_neighbor_evidence": [
            row.model_dump(mode="json")
            for row in repository.list_neighbor_evidence(seed.experiment_id)
            if row.channel == "sequence"
        ],
        "sequence_statuses": [
            row.model_dump(mode="json")
            for row in repository.list_neighbor_statuses(seed.experiment_id)
            if row.channel == "sequence"
        ],
    }


def main() -> None:
    args = parse_args()
    primary_id = args.experiment_id or _new_experiment_id()
    peer_id = f"{primary_id}_peer"
    for experiment_id in (primary_id, peer_id):
        _require(
            len(experiment_id) <= _EXPERIMENT_ID_MAX_LENGTH,
            f"experiment_id must be at most {_EXPERIMENT_ID_MAX_LENGTH} characters: "
            f"{experiment_id}",
        )

    settings = get_graph_settings()
    _require(
        bool(settings.password),
        "PTAGENT_GRAPH__PASSWORD must be set before running the Neo4j smoke",
    )
    primary = _make_seed(primary_id, token=_unique_token(primary_id, "primary"))
    peer = _make_seed(peer_id, token=_unique_token(peer_id, "peer"))
    repository = MySQLExperimentStore.from_settings()
    repository.initialize_schema()
    _seed_experiment(repository, primary)
    _seed_experiment(repository, peer)

    graph = Neo4jGraphStore(
        settings.uri, settings.user, settings.password, settings.database
    )
    try:
        graph.initialize_schema()
        connected = graph.run("RETURN 1 AS connected")
        _require(
            bool(connected and connected[0].get("connected") == 1),
            "Neo4j Bolt query did not return the expected result",
        )

        primary_summary = project_experiment_kg(
            primary.experiment_id, repository=repository, store=graph
        )
        peer_summary = project_experiment_kg(
            peer.experiment_id, repository=repository, store=graph
        )
        _assert_projection(graph, primary, primary_summary)
        _assert_projection(graph, peer, peer_summary)
        _assert_fusion_evidence_alignment(repository, primary)
        _assert_fusion_evidence_alignment(repository, peer)

        print("kg_state:")
        print(json.dumps(_kg_state(graph, primary), ensure_ascii=False, indent=2))
        print("structure_state:")
        print(json.dumps(_structure_state(repository, primary), ensure_ascii=False, indent=2))

        primary_counts = {
            "nodes": graph.count_nodes(
                scope=GraphScope.EXPERIMENT, experiment_id=primary.experiment_id
            ),
            "edges": graph.count_edges(
                scope=GraphScope.EXPERIMENT, experiment_id=primary.experiment_id
            ),
        }
        project_experiment_kg(primary.experiment_id, repository=repository, store=graph)
        _require(
            primary_counts
            == {
                "nodes": graph.count_nodes(
                    scope=GraphScope.EXPERIMENT, experiment_id=primary.experiment_id
                ),
                "edges": graph.count_edges(
                    scope=GraphScope.EXPERIMENT, experiment_id=primary.experiment_id
                ),
            },
            "re-projecting an experiment changed its workspace graph counts",
        )

        peer_before_cleanup = graph.count_edges(
            scope=GraphScope.EXPERIMENT, experiment_id=peer.experiment_id
        )
        removed_primary = graph.drop_experiment(primary.experiment_id)
        _require(removed_primary == 9, "primary workspace cleanup removed an unexpected count")
        _require(
            graph.count_nodes(
                scope=GraphScope.EXPERIMENT, experiment_id=primary.experiment_id
            )
            == 0,
            "primary workspace nodes remain after cleanup",
        )
        _require(
            graph.count_edges(
                scope=GraphScope.EXPERIMENT, experiment_id=primary.experiment_id
            )
            == 0,
            "primary workspace edges remain after cleanup",
        )
        _require(
            graph.count_edges(scope=GraphScope.EXPERIMENT, experiment_id=peer.experiment_id)
            == peer_before_cleanup,
            "primary workspace cleanup affected the peer experiment",
        )
        _require(
            any(
                link.disease_key == primary.conclusion_disease_id
                for link in graph.protein_diseases(
                    primary.gene_accession,
                    experiment_id=primary.experiment_id,
                )
            ),
            "primary cleanup removed a general knowledge-graph fact",
        )

        peer_removed = 0
        if not args.keep_peer_workspace:
            peer_removed = graph.drop_experiment(peer.experiment_id)
            _require(peer_removed == 9, "peer workspace cleanup removed an unexpected count")

        print("primary_experiment_id:", primary.experiment_id)
        print("peer_experiment_id:", peer.experiment_id)
        print("neo4j_uri:", settings.uri)
        print("neo4j_database:", settings.database)
        print("primary_projection:", primary_summary)
        print("peer_projection:", peer_summary)
        print("primary_reprojection_idempotent:", True)
        print("primary_workspace_removed:", removed_primary)
        print("peer_workspace_preserved_during_primary_cleanup:", True)
        print("general_fact_preserved:", True)
        print("peer_workspace_removed:", peer_removed)
    finally:
        graph.close()


if __name__ == "__main__":
    main()
