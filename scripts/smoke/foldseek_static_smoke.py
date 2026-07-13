"""Smoke test for the structure-neighbor path using a local Foldseek TSV fixture.

This does not run the real foldseek binary and does not require query structure
files. It verifies the PTAgent side of the structure path on real MySQL:
ExperimentBundle -> quantifications -> differential -> static structure provider
-> structure evidence -> generic neighbor evidence -> fused candidates -> report.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path


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
from pkg.experiment import (  # noqa: E402
    ExperimentBundle,
    ExperimentContext,
    ExperimentGroup,
    GroupRole,
    MySQLExperimentStore,
    PeptideRecord,
    ProteinQuantification,
    ProteinRecord,
)
from pkg.structure import StaticStructureSearchProvider  # noqa: E402


def _experiment_id(prefix: str) -> str:
    return prefix + datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _bundle(exp_id: str) -> ExperimentBundle:
    return ExperimentBundle(
        context=ExperimentContext(
            experiment_id=exp_id,
            session_id="foldseek_static_smoke",
            title="Foldseek static TSV smoke test",
            raw_text="Static Foldseek TSV + MySQL smoke test",
            disease=["structure-smoke"],
            pathway=["structure-neighbor"],
            organism="fixture",
            assay="DIA",
        ),
        groups=[
            ExperimentGroup(group_id="g_case", label="Case", role=GroupRole.CASE),
            ExperimentGroup(group_id="g_ctrl", label="Control", role=GroupRole.CONTROL),
        ],
        proteins=[
            ProteinRecord(
                protein_id="prot_static_query",
                accession="Q9RAT9",
                gene="STATIC_QUERY",
                organism="fixture",
                peptide_ids=["pep_static_query"],
                meta={
                    "note": (
                        "Q9RAT9 is used only because data/structure/static_neighbors.tsv "
                        "contains this query accession."
                    )
                },
            )
        ],
        peptides=[
            PeptideRecord(
                peptide_id="pep_static_query",
                peptidoform="PEPTIDEK",
                stripped_sequence="PEPTIDEK",
                protein_id="prot_static_query",
                spectrum_ids=["spec_static_query"],
                confidence=0.98,
                group_label="Case",
                abundance=1000.0,
            )
        ],
    )


def _quantifications(exp_id: str) -> list[ProteinQuantification]:
    return [
        ProteinQuantification(
            experiment_id=exp_id,
            protein_id="prot_static_query",
            group_id="g_case",
            sample_id="case_1",
            abundance=110.0,
        ),
        ProteinQuantification(
            experiment_id=exp_id,
            protein_id="prot_static_query",
            group_id="g_case",
            sample_id="case_2",
            abundance=120.0,
        ),
        ProteinQuantification(
            experiment_id=exp_id,
            protein_id="prot_static_query",
            group_id="g_ctrl",
            sample_id="ctrl_1",
            abundance=10.0,
        ),
        ProteinQuantification(
            experiment_id=exp_id,
            protein_id="prot_static_query",
            group_id="g_ctrl",
            sample_id="ctrl_2",
            abundance=11.0,
        ),
    ]


def _structure_provider(path: Path, *, min_score: float, top_k: int) -> StaticStructureSearchProvider:
    if not path.exists():
        raise FileNotFoundError(f"static Foldseek TSV not found: {path}")
    return StaticStructureSearchProvider(
        path.read_text(encoding="utf-8"),
        version="static-foldseek-fixture",
        top_k=top_k,
        min_score=min_score,
        min_coverage=0.0,
        exclude_self=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-id", default="", help="Optional fixed experiment_id.")
    parser.add_argument("--snapshot-version", default="1.0")
    parser.add_argument(
        "--static-neighbors-file",
        default="data/structure/static_neighbors.tsv",
        help="Foldseek-format TSV fixture.",
    )
    parser.add_argument("--min-score", type=float, default=0.5)
    parser.add_argument("--top-k", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    exp_id = args.experiment_id or _experiment_id("exp_foldseek_static_smoke_")
    static_path = Path(args.static_neighbors_file)
    if not static_path.is_absolute():
        static_path = PROJECT_ROOT / static_path

    store = MySQLExperimentStore.from_settings()
    store.initialize_schema()
    store.save_bundle(_bundle(exp_id))
    store.add_quantifications(_quantifications(exp_id))

    result = run_downstream_pipeline(
        exp_id,
        repository=store,
        config=DownstreamPipelineConfig(
            snapshot_version=args.snapshot_version,
            pipeline_version="foldseek-static-smoke",
            top_k=args.top_k,
            structure_provider=_structure_provider(
                static_path,
                min_score=args.min_score,
                top_k=args.top_k,
            ),
            neighbor_provider_names=("structure.foldseek",),
            allow_unresolved_hypotheses=True,
        ),
        steps=["differential", "neighbor_search", "freeze", "report"],
    )

    structure_runs = store.list_structure_search_runs(exp_id)
    structure_evidence = store.list_structure_neighbor_evidence(exp_id)
    neighbor_runs = store.list_neighbor_search_runs(exp_id)
    neighbor_evidence = store.list_neighbor_evidence(exp_id)
    fused_candidates = store.list_fused_candidates(exp_id)

    print("experiment_id:", exp_id)
    print("completed:", result.completed)
    print("failed_step:", result.failed_step)
    print("statuses:", result.step_statuses())
    print("pipeline_status:", pipeline_status(exp_id, repository=store))
    print("static_neighbors_file:", str(static_path))
    print("structure_search_runs:", len(structure_runs))
    print("structure_neighbor_evidence:", len(structure_evidence))
    print("neighbor_search_runs:", len(neighbor_runs))
    print("neighbor_evidence:", len(neighbor_evidence))
    print("fused_candidates:", len(fused_candidates))
    print("reports:", len(store.list_reports(exp_id)))

    for row in structure_evidence[:5]:
        print(
            "structure_evidence_preview:",
            row.query_accession,
            "->",
            row.target_accession,
            "score=",
            row.score,
            "rank=",
            row.rank,
        )
    for row in fused_candidates[:5]:
        print(
            "fused_candidate_preview:",
            row.query_accession,
            "->",
            row.target_id,
            "rank=",
            row.fusion_rank,
            "channels=",
            row.support_channels,
        )

    if not result.completed:
        raise SystemExit(1)
    if not structure_evidence or not neighbor_evidence or not fused_candidates:
        raise SystemExit("structure smoke produced no persisted neighbor evidence")


if __name__ == "__main__":
    main()
