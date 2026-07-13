"""Real Foldseek, UniProt FASTA, and InterPro/Pfam three-channel smoke test.

This test verifies the full path:

    AlphaFold model -> Foldseek structure neighbor
    UniProt FASTA -> sequence.kmer neighbor
    UniProt InterPro/Pfam assignments -> domain.interpro neighbor
    -> fused candidate -> KG candidate edge -> CTD hypothesis -> PubMed deep-search -> report

The structure, sequence, domain, and CTD inputs are real local data. The
accession-to-gene resolver remains a small static TSV fixture until a real
UniProt MCP is available. ``--include-deep-search`` enables the local PubMed
MCP before freezing; it is opt-in so routine runs remain offline.
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError


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

from application.orchestration import (  # noqa: E402
    DownstreamPipelineConfig,
    pipeline_status,
    run_downstream_pipeline,
)
from config import StructureSettings  # noqa: E402
from config.graph_settings import get_graph_settings  # noqa: E402
from pkg.disease import CTDFileDiseaseSource, StaticGeneResolver  # noqa: E402
from pkg.experiment import (  # noqa: E402
    EvidenceLevel,
    FusedCandidate,
    MetaAnnotation,
    MySQLExperimentStore,
)
from pkg.graph import (  # noqa: E402
    Direction,
    EdgeType,
    GraphEdge,
    InMemoryGraphStore,
    Neo4jGraphStore,
    NodeLabel,
    NodeRef,
)
from pkg.protein_db import parse_fasta  # noqa: E402
from pkg.retrieval.providers import (  # noqa: E402
    DomainNeighborProvider,
    SequenceNeighborProvider,
)
from pkg.structure import build_structure_search_provider  # noqa: E402

from foldseek_real_smoke import (  # noqa: E402
    _bundle,
    _experiment_id,
    _quantifications,
    _resolve_path,
    download_alphafold_cif,
)


def parse_args() -> argparse.Namespace:
    default_binary = os.environ.get(
        "PTAGENT_STRUCTURE__FOLDSEEK_BINARY",
        "/Users/tourbillion/foldseek/bin/foldseek",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-id", default="", help="Optional fixed experiment_id.")
    parser.add_argument("--snapshot-version", default="1.0")
    parser.add_argument("--accession", default="O60674", help="Query UniProt accession.")
    parser.add_argument("--gene", default="JAK2")
    parser.add_argument("--organism", default="Homo sapiens")
    parser.add_argument(
        "--expected-target-accession",
        default="Q09178",
        help="Target expected from structure, sequence, and domain channels.",
    )
    parser.add_argument(
        "--expected-target-gene",
        default="JAK1",
        help="Gene expected from the static accession-to-gene mapping.",
    )
    parser.add_argument("--foldseek-binary", default=default_binary)
    parser.add_argument(
        "--alphafold-db",
        default=os.environ.get(
            "PTAGENT_STRUCTURE__ALPHAFOLD_DB",
            "data/alphafold/afdb/alphafold_swissprot",
        ),
    )
    parser.add_argument(
        "--query-structure-dir",
        default=os.environ.get(
            "PTAGENT_STRUCTURE__QUERY_STRUCTURE_DIR",
            "data/structures",
        ),
    )
    parser.add_argument(
        "--sequence-fasta",
        default="data/sequences/uniprot_jak2_foldseek_neighbors_20260712.fasta",
    )
    parser.add_argument(
        "--sequence-version",
        default="uniprot-jak2-foldseek-neighbors-20260712",
    )
    parser.add_argument("--sequence-kmer", type=int, default=3)
    parser.add_argument(
        "--domain-data",
        default="data/domains/uniprot_interpro_pfam_jak2_foldseek_neighbors_20260712.json",
    )
    parser.add_argument(
        "--domain-manifest",
        default="data/domains/uniprot_interpro_pfam_jak2_foldseek_neighbors_20260712.manifest.json",
    )
    parser.add_argument("--domain-version", default="")
    parser.add_argument(
        "--gene-mapping-file",
        default=os.environ.get(
            "PTAGENT_ANNOTATION__STATIC_GENE_MAPPING_FILE",
            "data/structure/static_gene_mapping.tsv",
        ),
    )
    parser.add_argument(
        "--ctd-data-file",
        default=os.environ.get(
            "PTAGENT_CTD__DATA_FILE",
            "data/ctd/CTD_genes_diseases.direct.csv",
        ),
    )
    parser.add_argument("--ctd-version", default="CTD-local-direct-smoke")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--min-score", type=float, default=0.0)
    parser.add_argument("--min-coverage", type=float, default=0.0)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument(
        "--include-deep-search",
        action="store_true",
        help="Call the local PubMed MCP for generated hypotheses before freezing.",
    )
    parser.add_argument(
        "--graph-store",
        choices=("memory", "neo4j"),
        default="memory",
        help="Project the KG into memory or the configured Neo4j service.",
    )
    parser.add_argument(
        "--keep-neo4j-workspace",
        action="store_true",
        help="Keep this smoke test's EXPERIMENT-scoped Neo4j workspace.",
    )
    parser.add_argument(
        "--expect-candidate-fallback",
        action="store_true",
        help=(
            "Assert that the selected hypothesis used candidate-gene PubMed fallback "
            "and that the fallback evidence was frozen into the snapshot."
        ),
    )
    parser.add_argument(
        "--expected-fallback-gene",
        default="JAK1",
        help="Candidate gene expected when --expect-candidate-fallback is enabled.",
    )
    parser.add_argument(
        "--expected-fallback-disease",
        default="Lupus Nephritis",
        help="Disease expected in the candidate fallback query.",
    )
    return parser.parse_args()


def _resolved_foldseek_binary(value: str) -> str:
    return str(_resolve_path(value)) if "/" in value else value


def _load_fasta_sequences(path: Path) -> dict[str, str]:
    entries = parse_fasta(path)
    return {
        accession: sequence
        for accession, (_description, sequence) in entries.items()
        if accession and sequence
    }


def _load_domain_assignments(
    data_path: Path, manifest_path: Path
) -> tuple[dict[str, list[str]], str, str]:
    data_bytes = data_path.read_bytes()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual_sha256 = hashlib.sha256(data_bytes).hexdigest()
    expected_sha256 = str(manifest.get("dataset_sha256") or "")
    if actual_sha256 != expected_sha256:
        raise SystemExit(
            "domain dataset checksum mismatch: "
            f"expected {expected_sha256}, got {actual_sha256}"
        )
    payload = json.loads(data_bytes)
    raw_domains = payload.get("domains")
    if not isinstance(raw_domains, dict):
        raise SystemExit("domain dataset must contain a domains mapping")
    domains = {
        str(accession): [str(domain) for domain in domain_ids]
        for accession, domain_ids in raw_domains.items()
        if isinstance(domain_ids, list)
    }
    if not domains:
        raise SystemExit("domain dataset contains no domain assignments")
    return domains, str(payload.get("dataset_id") or ""), actual_sha256


def _find_expected_hypothesis(
    annotations: list[MetaAnnotation], target_accession: str
) -> MetaAnnotation | None:
    for annotation in annotations:
        if annotation.evidence_level is not EvidenceLevel.HYPOTHESIS:
            continue
        neighbors = annotation.derivation.get("neighbors", [])
        if any(row.get("accession") == target_accession for row in neighbors):
            return annotation
    return None


def _find_fused_candidate(
    candidates: list[FusedCandidate], target_accession: str
) -> FusedCandidate | None:
    return next((row for row in candidates if row.target_id == target_accession), None)


def _has_edge_to(edges: list[GraphEdge], target_accession: str) -> bool:
    return any(edge.end.key == target_accession for edge in edges)


def main() -> None:
    args = parse_args()
    if args.expect_candidate_fallback and not args.include_deep_search:
        raise SystemExit("--expect-candidate-fallback requires --include-deep-search")
    exp_id = args.experiment_id or _experiment_id("exp_fs_seq_dom_hyp_smoke_")
    if len(exp_id) > _EXPERIMENT_ID_MAX_LENGTH:
        raise SystemExit(
            f"experiment_id must be at most {_EXPERIMENT_ID_MAX_LENGTH} characters: {exp_id}"
        )
    accession = args.accession.strip()
    if not accession:
        raise SystemExit("--accession must be non-empty")
    if args.sequence_kmer < 1:
        raise SystemExit("--sequence-kmer must be positive")

    query_structure_dir = _resolve_path(args.query_structure_dir)
    alphafold_db = _resolve_path(args.alphafold_db)
    sequence_fasta = _resolve_path(args.sequence_fasta)
    domain_data = _resolve_path(args.domain_data)
    domain_manifest = _resolve_path(args.domain_manifest)
    mapping_file = _resolve_path(args.gene_mapping_file)
    ctd_file = _resolve_path(args.ctd_data_file)
    foldseek_binary = _resolved_foldseek_binary(args.foldseek_binary)

    for label, path in (
        ("sequence FASTA", sequence_fasta),
        ("domain dataset", domain_data),
        ("domain manifest", domain_manifest),
        ("static gene mapping", mapping_file),
        ("CTD direct-evidence file", ctd_file),
    ):
        if not path.exists():
            raise SystemExit(f"{label} not found: {path}")

    sequences = _load_fasta_sequences(sequence_fasta)
    domains, dataset_id, domain_sha256 = _load_domain_assignments(
        domain_data, domain_manifest
    )
    required_accessions = {accession, args.expected_target_accession}
    missing_sequences = sorted(required_accessions - set(sequences))
    missing_domains = sorted(required_accessions - set(domains))
    if missing_sequences:
        raise SystemExit(f"sequence FASTA is missing required accessions: {missing_sequences}")
    if missing_domains:
        raise SystemExit(f"domain dataset is missing required accessions: {missing_domains}")

    sequence_provider = SequenceNeighborProvider(
        sequences,
        version=args.sequence_version,
        top_k=args.top_k,
        k_kmer=args.sequence_kmer,
    )
    domain_version = args.domain_version or dataset_id
    domain_provider = DomainNeighborProvider(
        domains,
        version=domain_version,
        top_k=args.top_k,
    )
    sequence_preview = sequence_provider.search([accession], top_k=args.top_k).candidates
    domain_preview = domain_provider.search([accession], top_k=args.top_k).candidates
    expected_sequence_hit = next(
        (
            row
            for row in sequence_preview
            if row.target_accession == args.expected_target_accession
        ),
        None,
    )
    expected_domain_hit = next(
        (
            row
            for row in domain_preview
            if row.target_accession == args.expected_target_accession
        ),
        None,
    )
    if expected_sequence_hit is None or expected_domain_hit is None:
        raise SystemExit(
            "expected target was not recalled by sequence or domain; "
            "increase --top-k or inspect the input datasets"
        )

    gene_resolver = StaticGeneResolver.from_file(mapping_file)
    expected_gene = gene_resolver.resolve([args.expected_target_accession]).get(
        args.expected_target_accession
    )
    if expected_gene != args.expected_target_gene:
        raise SystemExit(
            "static gene mapping does not contain the expected target mapping: "
            f"{args.expected_target_accession} -> {args.expected_target_gene}"
        )
    disease_source = CTDFileDiseaseSource.from_file(ctd_file, version=args.ctd_version)
    target_diseases = disease_source.fetch([args.expected_target_gene]).get(
        args.expected_target_gene, []
    )
    if not target_diseases:
        raise SystemExit(
            f"CTD source has no direct disease facts for {args.expected_target_gene}"
        )

    downloaded, af_record = download_alphafold_cif(
        accession,
        query_structure_dir=query_structure_dir,
        timeout=args.timeout,
        force=args.force_download,
    )
    latest_version = str(af_record.get("latestVersion") or "unknown")

    store = MySQLExperimentStore.from_settings()
    store.initialize_schema()
    store.save_bundle(_bundle(exp_id, accession, args.gene, args.organism))
    store.add_quantifications(_quantifications(exp_id, accession))

    structure_settings = StructureSettings(
        provider="foldseek",
        foldseek_binary=foldseek_binary,
        alphafold_db=str(alphafold_db),
        query_structure_dir=str(query_structure_dir),
        top_k=args.top_k,
        min_score=args.min_score,
        min_coverage=args.min_coverage,
        exclude_self=True,
        version=f"alphafold-v{latest_version}-three-channel-smoke-{exp_id}",
    )
    if args.graph_store == "neo4j":
        graph_settings = get_graph_settings()
        graph = Neo4jGraphStore(
            graph_settings.uri,
            graph_settings.user,
            graph_settings.password,
            graph_settings.database,
            connection_timeout=graph_settings.connection_timeout_seconds,
            max_connection_lifetime=graph_settings.max_connection_lifetime_seconds,
            max_transaction_retry_time=graph_settings.max_transaction_retry_seconds,
        )
        graph.initialize_schema()

        def cleanup_neo4j_workspace() -> None:
            if not args.keep_neo4j_workspace:
                graph.drop_experiment(exp_id)
            graph.close()

        atexit.register(cleanup_neo4j_workspace)
    else:
        graph = InMemoryGraphStore()
    pipeline_steps = [
        "ctd_disease",
        "differential",
        "neighbor_search",
        "hypothesis",
        "kg_projection",
    ]
    if args.include_deep_search:
        pipeline_steps.append("deep_search")
    pipeline_steps.extend(("freeze", "report"))
    result = run_downstream_pipeline(
        exp_id,
        repository=store,
        config=DownstreamPipelineConfig(
            snapshot_version=args.snapshot_version,
            pipeline_version=(
                "foldseek-sequence-domain-hypothesis-real-smoke-pubmed"
                if args.include_deep_search
                else "foldseek-sequence-domain-hypothesis-real-smoke"
            ),
            top_k=args.top_k,
            disease_source=disease_source,
            gene_resolver=gene_resolver,
            structure_provider=build_structure_search_provider(structure_settings),
            neighbor_provider_names=(
                "structure.foldseek",
                "sequence.kmer",
                "domain.interpro",
            ),
            neighbor_provider_options={
                "sequence.kmer": {
                    "sequences": sequences,
                    "version": args.sequence_version,
                    "k_kmer": args.sequence_kmer,
                },
                "domain.interpro": {
                    "domains": domains,
                    "version": domain_version,
                },
            },
            graph_store=graph,
            allow_unresolved_hypotheses=not args.include_deep_search,
        ),
        steps=pipeline_steps,
    )

    annotations = store.list_annotations(exp_id)
    structure_evidence = store.list_structure_neighbor_evidence(exp_id)
    neighbor_runs = store.list_neighbor_search_runs(exp_id)
    neighbor_evidence = store.list_neighbor_evidence(exp_id)
    fused_candidates = store.list_fused_candidates(exp_id)
    hypothesis = _find_expected_hypothesis(annotations, args.expected_target_accession)
    fused_candidate = _find_fused_candidate(
        fused_candidates, args.expected_target_accession
    )
    structural_edges = graph.neighbors(
        NodeRef(NodeLabel.PROTEIN, accession),
        EdgeType.STRUCTURAL_NEIGHBOR,
        direction=Direction.OUT,
    )
    candidate_edges = graph.neighbors(
        NodeRef(NodeLabel.PROTEIN, accession),
        EdgeType.CANDIDATE_NEIGHBOR,
        direction=Direction.OUT,
        experiment_id=exp_id,
    )
    disease_links = graph.protein_diseases(accession, experiment_id=exp_id)
    reports = store.list_reports(exp_id)
    deep_search_evidence = store.list_deep_search_evidence(exp_id)
    annotation_history = store.list_annotation_history(exp_id)
    snapshots = store.list_snapshots(exp_id)
    sequence_runs = [row for row in neighbor_runs if row.provider_id == "sequence.kmer"]
    domain_runs = [row for row in neighbor_runs if row.provider_id == "domain.interpro"]
    sequence_evidence = [row for row in neighbor_evidence if row.channel == "sequence"]
    domain_evidence = [row for row in neighbor_evidence if row.channel == "domain"]
    expected_sequence_evidence = any(
        row.target_id == args.expected_target_accession for row in sequence_evidence
    )
    expected_domain_evidence = any(
        row.target_id == args.expected_target_accession for row in domain_evidence
    )
    expected_structural_edge = _has_edge_to(
        structural_edges, args.expected_target_accession
    )
    expected_candidate_edge = _has_edge_to(
        candidate_edges, args.expected_target_accession
    )
    kg_summary = next(
        (step.summary for step in result.steps if step.name == "kg_projection"),
        {},
    )

    print("experiment_id:", exp_id)
    print("graph_store:", args.graph_store)
    print("completed:", result.completed)
    print("failed_step:", result.failed_step)
    print("statuses:", result.step_statuses())
    print("pipeline_status:", pipeline_status(exp_id, repository=store))
    print("downloaded_structure:", str(downloaded))
    print("alphafold_latest_version:", latest_version)
    print("foldseek_binary:", foldseek_binary)
    print("alphafold_db:", str(alphafold_db))
    print("sequence_fasta:", str(sequence_fasta))
    print("sequence_catalog_entries:", len(sequences))
    print("sequence_version:", args.sequence_version)
    print("domain_data:", str(domain_data))
    print("domain_manifest:", str(domain_manifest))
    print("domain_catalog_entries:", len(domains))
    print("domain_version:", domain_version)
    print("domain_dataset_sha256:", domain_sha256)
    print("expected_target:", args.expected_target_accession, "->", args.expected_target_gene)
    print("sequence_preview_rank:", expected_sequence_hit.rank)
    print("sequence_preview_score:", expected_sequence_hit.score)
    print("domain_preview_rank:", expected_domain_hit.rank)
    print("domain_preview_jaccard:", expected_domain_hit.score)
    print("domain_preview_shared_count:", expected_domain_hit.meta["shared_domain_count"])
    print("structure_neighbor_evidence:", len(structure_evidence))
    print("sequence_neighbor_runs:", len(sequence_runs))
    print("sequence_neighbor_evidence:", len(sequence_evidence))
    print("domain_neighbor_runs:", len(domain_runs))
    print("domain_neighbor_evidence:", len(domain_evidence))
    print("fused_candidates:", len(fused_candidates))
    print("ctd_conclusions:", sum(a.evidence_level is EvidenceLevel.CONCLUSION for a in annotations))
    print("hypotheses:", sum(a.evidence_level is EvidenceLevel.HYPOTHESIS for a in annotations))
    print("kg_structural_edges:", len(structural_edges))
    print("kg_candidate_edges:", len(candidate_edges))
    print("kg_projection_skipped:", kg_summary.get("projection_skipped", {}))
    print("kg_expected_structural_edge:", expected_structural_edge)
    print("kg_expected_candidate_edge:", expected_candidate_edge)
    print(
        "kg_hypothesis_links:",
        sum(link.evidence_level == "HYPOTHESIS" for link in disease_links),
    )
    print("deep_search_enabled:", args.include_deep_search)
    print("deep_search_evidence:", len(deep_search_evidence))
    print("annotation_history:", len(annotation_history))
    print("reports:", len(reports))

    expected_primary_query = (
        f"({args.gene}) AND ({args.expected_fallback_disease}) "
        f"AND ({args.organism})"
    )
    expected_fallback_query = (
        f"({args.expected_fallback_gene}) AND ({args.expected_fallback_disease})"
    )
    fallback_evidence = [
        row
        for row in deep_search_evidence
        if row.provenance.get("query_scope") == "candidate_fallback"
        and row.provenance.get("candidate_gene") == args.expected_fallback_gene
        and row.provenance.get("primary_query") == expected_primary_query
        and row.provenance.get("query") == expected_fallback_query
    ]
    snapshot_fallback_evidence = []
    if snapshots:
        snapshot_fallback_evidence = [
            row
            for row in snapshots[0].manifest.get("deep_search_evidence", [])
            if (row.get("provenance") or {}).get("query_scope")
            == "candidate_fallback"
            and (row.get("provenance") or {}).get("candidate_gene")
            == args.expected_fallback_gene
            and (row.get("provenance") or {}).get("primary_query")
            == expected_primary_query
            and (row.get("provenance") or {}).get("query") == expected_fallback_query
        ]
    if args.expect_candidate_fallback:
        print("candidate_fallback_evidence:", len(fallback_evidence))
        print("candidate_fallback_gene:", args.expected_fallback_gene)
        print("candidate_fallback_primary_query:", expected_primary_query)
        print("candidate_fallback_query:", expected_fallback_query)
        print("candidate_fallback_snapshot_evidence:", len(snapshot_fallback_evidence))

    for candidate in sorted(
        fused_candidates,
        key=lambda row: (row.fusion_rank, -row.fused_score, row.target_id),
    ):
        print(
            "fused_candidate:",
            candidate.query_accession,
            "->",
            candidate.target_id,
            "rank=",
            candidate.fusion_rank,
            "score=",
            f"{candidate.fused_score:.8f}",
            "channels=",
            candidate.support_channels,
        )
    if hypothesis is not None:
        print(
            "hypothesis_preview:",
            hypothesis.target,
            "->",
            hypothesis.value.get("disease_id"),
            hypothesis.value.get("disease_name"),
            "via=",
            hypothesis.derivation.get("via_genes"),
        )
    if reports:
        print(
            "report_has_hypothesis:",
            bool(hypothesis and hypothesis.annotation_id in reports[0].content),
        )

    expected_three_channel_candidate = bool(
        fused_candidate
        and {"structure", "sequence", "domain"}.issubset(
            fused_candidate.support_channels
        )
    )
    has_hypothesis_link = any(link.evidence_level == "HYPOTHESIS" for link in disease_links)
    report_has_hypothesis = bool(
        reports and hypothesis and hypothesis.annotation_id in reports[0].content
    )
    if not result.completed:
        raise SystemExit(1)
    if (
        not structure_evidence
        or not sequence_runs
        or not sequence_evidence
        or not domain_runs
        or not domain_evidence
    ):
        raise SystemExit("one or more neighbor channels produced no persisted evidence")
    if not expected_sequence_evidence or not expected_domain_evidence:
        raise SystemExit("expected target is missing from sequence or domain evidence")
    if not expected_three_channel_candidate:
        raise SystemExit("expected target did not receive structure, sequence, and domain support")
    if not expected_structural_edge or not expected_candidate_edge:
        raise SystemExit("KG projection is missing the expected structural or candidate edge")
    if not hypothesis or not has_hypothesis_link or not report_has_hypothesis:
        raise SystemExit("hypothesis, KG disease link, or report evidence is missing")
    if args.include_deep_search and (not deep_search_evidence or not annotation_history):
        raise SystemExit("real PubMed deep-search did not persist evidence and history")
    if args.expect_candidate_fallback:
        if not fallback_evidence:
            raise SystemExit(
                "expected PubMed candidate fallback evidence was not persisted for "
                f"{args.expected_fallback_gene} and {args.expected_fallback_disease}"
            )
        if not snapshots:
            raise SystemExit("candidate fallback evidence was not frozen into a snapshot")
        persisted_fallback_ids = {row.evidence_id for row in fallback_evidence}
        snapshot_fallback_ids = {
            str(row.get("evidence_id") or "") for row in snapshot_fallback_evidence
        }
        if persisted_fallback_ids != snapshot_fallback_ids:
            raise SystemExit(
                "candidate fallback evidence differs between live store and frozen snapshot"
            )


if __name__ == "__main__":
    try:
        main()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise SystemExit(f"AlphaFold download failed: {type(exc).__name__}: {exc}") from exc
