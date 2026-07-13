"""Real AlphaFold/Foldseek neighbor-to-hypothesis smoke test.

The test downloads the human JAK2 AlphaFold model, searches it against the
local AlphaFold Foldseek database, and verifies this persisted chain:

    structure evidence -> fused candidate -> CTD-backed hypothesis -> KG -> report

The query and the Foldseek search are real. Candidate accession-to-gene
resolution uses a small local TSV fixture because a real UniProt MCP is not
available in this development environment. Hypotheses emitted by this script
remain candidates for deep-search validation; they are not biological findings.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError


PROJECT_ROOT = Path(__file__).resolve().parents[2]
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
from pkg.disease import CTDFileDiseaseSource, StaticGeneResolver  # noqa: E402
from pkg.experiment import EvidenceLevel, MySQLExperimentStore  # noqa: E402
from pkg.graph import Direction, EdgeType, InMemoryGraphStore, NodeLabel, NodeRef  # noqa: E402
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
        help="Known local-DB Foldseek hit required for this smoke test.",
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
    return parser.parse_args()


def _resolved_foldseek_binary(value: str) -> str:
    return str(_resolve_path(value)) if "/" in value else value


def _find_expected_hypothesis(annotations, target_accession: str):
    for annotation in annotations:
        if annotation.evidence_level is not EvidenceLevel.HYPOTHESIS:
            continue
        neighbors = annotation.derivation.get("neighbors", [])
        if any(row.get("accession") == target_accession for row in neighbors):
            return annotation
    return None


def main() -> None:
    args = parse_args()
    exp_id = args.experiment_id or _experiment_id("exp_foldseek_hypothesis_real_smoke_")
    accession = args.accession.strip()
    if not accession:
        raise SystemExit("--accession must be non-empty")

    query_structure_dir = _resolve_path(args.query_structure_dir)
    alphafold_db = _resolve_path(args.alphafold_db)
    mapping_file = _resolve_path(args.gene_mapping_file)
    ctd_file = _resolve_path(args.ctd_data_file)
    foldseek_binary = _resolved_foldseek_binary(args.foldseek_binary)

    if not mapping_file.exists():
        raise SystemExit(f"static gene mapping file not found: {mapping_file}")
    if not ctd_file.exists():
        raise SystemExit(f"CTD direct-evidence file not found: {ctd_file}")

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
        version=f"alphafold-v{latest_version}-hypothesis-smoke-{exp_id}",
    )
    graph = InMemoryGraphStore()
    result = run_downstream_pipeline(
        exp_id,
        repository=store,
        config=DownstreamPipelineConfig(
            snapshot_version=args.snapshot_version,
            pipeline_version="foldseek-hypothesis-real-smoke",
            top_k=args.top_k,
            disease_source=disease_source,
            gene_resolver=gene_resolver,
            structure_provider=build_structure_search_provider(structure_settings),
            neighbor_provider_names=("structure.foldseek",),
            graph_store=graph,
            # The smoke intentionally stops before deep-search. Do not use this
            # switch when freezing a scientific result for delivery.
            allow_unresolved_hypotheses=True,
        ),
        steps=[
            "ctd_disease",
            "differential",
            "neighbor_search",
            "hypothesis",
            "kg_projection",
            "freeze",
            "report",
        ],
    )

    annotations = store.list_annotations(exp_id)
    structure_evidence = store.list_structure_neighbor_evidence(exp_id)
    fused_candidates = store.list_fused_candidates(exp_id)
    hypothesis = _find_expected_hypothesis(annotations, args.expected_target_accession)
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
    kg_summary = next(
        (step.summary for step in result.steps if step.name == "kg_projection"),
        {},
    )
    projection_skipped = kg_summary.get("projection_skipped", {})
    expected_structural_edge = any(
        edge.end.key == args.expected_target_accession for edge in structural_edges
    )

    print("experiment_id:", exp_id)
    print("completed:", result.completed)
    print("failed_step:", result.failed_step)
    print("statuses:", result.step_statuses())
    print("pipeline_status:", pipeline_status(exp_id, repository=store))
    print("downloaded_structure:", str(downloaded))
    print("alphafold_latest_version:", latest_version)
    print("alphafold_cif_url:", af_record.get("cifUrl"))
    print("foldseek_binary:", foldseek_binary)
    print("alphafold_db:", str(alphafold_db))
    print("static_gene_mapping:", str(mapping_file))
    print("ctd_data_file:", str(ctd_file))
    print("expected_target:", args.expected_target_accession, "->", args.expected_target_gene)
    print("structure_neighbor_evidence:", len(structure_evidence))
    print("fused_candidates:", len(fused_candidates))
    print(
        "ctd_conclusions:",
        sum(a.evidence_level is EvidenceLevel.CONCLUSION for a in annotations),
    )
    print(
        "hypotheses:",
        sum(a.evidence_level is EvidenceLevel.HYPOTHESIS for a in annotations),
    )
    print("kg_structural_edges:", len(structural_edges))
    print("kg_candidate_edges:", len(candidate_edges))
    print("kg_projection_skipped:", projection_skipped)
    print("kg_expected_structural_edge:", expected_structural_edge)
    print(
        "kg_hypothesis_links:",
        sum(link.evidence_level == "HYPOTHESIS" for link in disease_links),
    )
    print("reports:", len(reports))

    for row in structure_evidence[:5]:
        print(
            "structure_evidence_preview:",
            row.query_accession,
            "->",
            row.target_accession,
            "score=",
            row.score,
            "coverage=",
            row.coverage,
            "rank=",
            row.rank,
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
            "report_has_hypothesis_section:",
            bool(hypothesis and hypothesis.annotation_id in reports[0].content),
        )

    expected_candidate = any(
        row.target_id == args.expected_target_accession for row in fused_candidates
    )
    has_hypothesis_link = any(link.evidence_level == "HYPOTHESIS" for link in disease_links)
    report_has_hypothesis_section = bool(
        reports and hypothesis and hypothesis.annotation_id in reports[0].content
    )
    if not result.completed:
        raise SystemExit(1)
    if not structure_evidence or not fused_candidates:
        raise SystemExit("real Foldseek smoke produced no persisted neighbor evidence")
    if not expected_candidate:
        raise SystemExit(
            f"expected real Foldseek candidate not found: {args.expected_target_accession}"
        )
    if hypothesis is None:
        raise SystemExit(
            "expected candidate did not produce a CTD-backed protein hypothesis; "
            "inspect resolver and CTD previews above"
        )
    if not structural_edges or not expected_structural_edge or not has_hypothesis_link:
        raise SystemExit("KG projection is missing the expected structural or hypothesis edge")
    if not report_has_hypothesis_section:
        raise SystemExit("report did not render the structure-hypothesis section")


if __name__ == "__main__":
    try:
        main()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise SystemExit(f"AlphaFold download failed: {type(exc).__name__}: {exc}") from exc
