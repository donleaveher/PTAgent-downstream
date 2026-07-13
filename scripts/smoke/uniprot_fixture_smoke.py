"""Smoke test for the UniProt annotation write path using local fixtures.

This does not call the real UniProt MCP provider. It verifies the PTAgent side:
fixture UniProt-like facts -> MetaAnnotation(CONCLUSION) -> CTD/differential/
enrichment -> freeze -> report on the real MySQL experiment fact store.
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
from pkg.annotation import ProteinAnnotationFact  # noqa: E402
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


class FixtureUniProtSource:
    """Small local source that mimics normalized UniProt MCP facts."""

    name = "UniProt-Fixture"
    version = "fixture-2026-07"

    def __init__(self) -> None:
        self.requests: list[list[str]] = []

    def fetch(self, accessions: list[str]) -> dict[str, list[ProteinAnnotationFact]]:
        unique = sorted({accession for accession in accessions if accession})
        self.requests.append(unique)
        facts: dict[str, list[ProteinAnnotationFact]] = {
            "Q9RAT9": [
                ProteinAnnotationFact(
                    accession="Q9RAT9",
                    attribute="organism",
                    value="Rattus norvegicus",
                    source_ref="UniProt:Q9RAT9#organism",
                    provenance={"fixture_field": "organism"},
                ),
                ProteinAnnotationFact(
                    accession="Q9RAT9",
                    attribute="gene",
                    value="JAK2",
                    source_ref="UniProt:Q9RAT9#gene",
                    provenance={"fixture_field": "gene"},
                ),
                ProteinAnnotationFact(
                    accession="Q9RAT9",
                    attribute="domain",
                    value="protein kinase domain",
                    source_ref="UniProt:Q9RAT9#domain",
                    provenance={"fixture_field": "domain"},
                ),
                ProteinAnnotationFact(
                    accession="Q9RAT9",
                    attribute="go",
                    value="GO:0004713",
                    source_ref="UniProt:Q9RAT9#go",
                    evidence_code="ECO:0000256",
                    provenance={"fixture_field": "go"},
                ),
            ],
            "P40763": [
                ProteinAnnotationFact(
                    accession="P40763",
                    attribute="organism",
                    value="Homo sapiens",
                    source_ref="UniProt:P40763#organism",
                    provenance={"fixture_field": "organism"},
                ),
                ProteinAnnotationFact(
                    accession="P40763",
                    attribute="gene",
                    value="STAT3",
                    source_ref="UniProt:P40763#gene",
                    provenance={"fixture_field": "gene"},
                ),
                ProteinAnnotationFact(
                    accession="P40763",
                    attribute="domain",
                    value="SH2 domain",
                    source_ref="UniProt:P40763#domain",
                    provenance={"fixture_field": "domain"},
                ),
                ProteinAnnotationFact(
                    accession="P40763",
                    attribute="go",
                    value="GO:0007165",
                    source_ref="UniProt:P40763#go",
                    evidence_code="ECO:0000269",
                    provenance={"fixture_field": "go"},
                ),
                ProteinAnnotationFact(
                    accession="P40763",
                    attribute="interpro",
                    value="IPR001217",
                    source_ref="UniProt:P40763#interpro",
                    provenance={"fixture_field": "interpro"},
                ),
            ],
        }
        return {accession: facts[accession] for accession in unique if accession in facts}


def _experiment_id(prefix: str) -> str:
    return prefix + datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _bundle(exp_id: str) -> ExperimentBundle:
    return ExperimentBundle(
        context=ExperimentContext(
            experiment_id=exp_id,
            session_id="uniprot_fixture_smoke",
            title="UniProt fixture MySQL smoke test",
            raw_text="Fixture UniProt + real CTD + MySQL smoke test",
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
    exp_id = args.experiment_id or _experiment_id("exp_uniprot_fixture_smoke_")
    source = FixtureUniProtSource()

    store = MySQLExperimentStore.from_settings()
    store.initialize_schema()
    store.save_bundle(_bundle(exp_id))
    store.add_quantifications(_quantifications(exp_id))

    result = run_downstream_pipeline(
        exp_id,
        repository=store,
        config=DownstreamPipelineConfig(
            snapshot_version=args.snapshot_version,
            pipeline_version="uniprot-fixture-smoke",
            enrichment_min_overlap=args.enrichment_min_overlap,
            annotation_source=source,
        ),
        steps=[
            "base_annotation",
            "ctd_disease",
            "differential",
            "enrichment",
            "freeze",
            "report",
        ],
    )

    annotations = store.list_annotations(exp_id)
    uniprot_rows = [row for row in annotations if row.source == source.name]
    ctd_rows = [row for row in annotations if row.source == "CTD"]
    enrichments = store.list_enrichments(exp_id)

    print("experiment_id:", exp_id)
    print("completed:", result.completed)
    print("failed_step:", result.failed_step)
    print("statuses:", result.step_statuses())
    print("pipeline_status:", pipeline_status(exp_id, repository=store))
    print("fixture_requests:", source.requests)
    print("uniprot_fixture_annotations:", len(uniprot_rows))
    print("ctd_annotations:", len(ctd_rows))
    print("enrichments:", len(enrichments))
    print("reports:", len(store.list_reports(exp_id)))

    for row in uniprot_rows[:6]:
        print("uniprot_preview:", row.target, row.attribute, row.value)

    if not result.completed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
