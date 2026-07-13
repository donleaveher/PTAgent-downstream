"""Smoke test for real CTD data on the real MySQL experiment fact store.

This verifies:
schema init -> ExperimentBundle -> quantifications -> CTD annotations ->
differential -> enrichment -> freeze -> report.
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
os.environ.setdefault("PTAGENT_CTD__DATA_FILE", "data/ctd/CTD_genes_diseases.direct.csv")
os.environ.setdefault("PTAGENT_CTD__VERSION", "CTD-2026-06")

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


def _experiment_id(prefix: str) -> str:
    return prefix + datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _bundle(exp_id: str) -> ExperimentBundle:
    return ExperimentBundle(
        context=ExperimentContext(
            experiment_id=exp_id,
            session_id="ctd_smoke",
            title="CTD MySQL smoke test",
            raw_text="Real CTD + MySQL smoke test",
            disease=["CIRI"],
            pathway=["JAK2/STAT3"],
            organism="Rattus norvegicus",
            taxon_id=10116,
            assay="DIA",
        ),
        groups=[
            ExperimentGroup(group_id="g_case", label="Case", role=GroupRole.CASE),
            ExperimentGroup(group_id="g_ctrl", label="Control", role=GroupRole.CONTROL),
        ],
        proteins=[
            ProteinRecord(
                protein_id="prot_jak2",
                accession="Q9RAT9",
                gene="JAK2",
                organism="Rattus norvegicus",
                taxon_id=10116,
                peptide_ids=["pep_jak2"],
            ),
            ProteinRecord(
                protein_id="prot_stat3",
                accession="P40763",
                gene="STAT3",
                organism="Homo sapiens",
                taxon_id=9606,
                peptide_ids=["pep_stat3"],
            ),
        ],
        peptides=[
            PeptideRecord(
                peptide_id="pep_jak2",
                peptidoform="PEPTIDEK",
                stripped_sequence="PEPTIDEK",
                protein_id="prot_jak2",
                spectrum_ids=["spec_1"],
                confidence=0.98,
                group_label="Case",
                abundance=1000.0,
            ),
            PeptideRecord(
                peptide_id="pep_stat3",
                peptidoform="STATPEPK",
                stripped_sequence="STATPEPK",
                protein_id="prot_stat3",
                spectrum_ids=["spec_2"],
                confidence=0.97,
                group_label="Control",
                abundance=900.0,
            ),
        ],
    )


def _quantifications(exp_id: str) -> list[ProteinQuantification]:
    return [
        ProteinQuantification(
            experiment_id=exp_id,
            protein_id="prot_jak2",
            group_id="g_case",
            sample_id="case_1",
            abundance=110.0,
        ),
        ProteinQuantification(
            experiment_id=exp_id,
            protein_id="prot_jak2",
            group_id="g_case",
            sample_id="case_2",
            abundance=120.0,
        ),
        ProteinQuantification(
            experiment_id=exp_id,
            protein_id="prot_jak2",
            group_id="g_ctrl",
            sample_id="ctrl_1",
            abundance=10.0,
        ),
        ProteinQuantification(
            experiment_id=exp_id,
            protein_id="prot_jak2",
            group_id="g_ctrl",
            sample_id="ctrl_2",
            abundance=11.0,
        ),
        ProteinQuantification(
            experiment_id=exp_id,
            protein_id="prot_stat3",
            group_id="g_case",
            sample_id="case_1",
            abundance=50.0,
        ),
        ProteinQuantification(
            experiment_id=exp_id,
            protein_id="prot_stat3",
            group_id="g_case",
            sample_id="case_2",
            abundance=51.0,
        ),
        ProteinQuantification(
            experiment_id=exp_id,
            protein_id="prot_stat3",
            group_id="g_ctrl",
            sample_id="ctrl_1",
            abundance=49.0,
        ),
        ProteinQuantification(
            experiment_id=exp_id,
            protein_id="prot_stat3",
            group_id="g_ctrl",
            sample_id="ctrl_2",
            abundance=50.0,
        ),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-id", default="", help="Optional fixed experiment_id.")
    parser.add_argument("--snapshot-version", default="1.0")
    parser.add_argument("--enrichment-min-overlap", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    exp_id = args.experiment_id or _experiment_id("exp_ctd_smoke_")

    store = MySQLExperimentStore.from_settings()
    store.initialize_schema()
    store.save_bundle(_bundle(exp_id))
    store.add_quantifications(_quantifications(exp_id))

    result = run_downstream_pipeline(
        exp_id,
        repository=store,
        config=DownstreamPipelineConfig(
            snapshot_version=args.snapshot_version,
            pipeline_version="ctd-mysql-smoke",
            enrichment_min_overlap=args.enrichment_min_overlap,
        ),
        steps=["ctd_disease", "differential", "enrichment", "freeze", "report"],
    )

    annotations = store.list_annotations(exp_id)
    enrichments = store.list_enrichments(exp_id)

    print("experiment_id:", exp_id)
    print("completed:", result.completed)
    print("failed_step:", result.failed_step)
    print("statuses:", result.step_statuses())
    print("pipeline_status:", pipeline_status(exp_id, repository=store))
    print("ctd_annotations:", len([row for row in annotations if row.source == "CTD"]))
    print("enrichments:", len(enrichments))
    print("reports:", len(store.list_reports(exp_id)))

    for row in annotations[:5]:
        print("annotation_preview:", row.target, row.attribute, row.value)

    if not result.completed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
