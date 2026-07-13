"""Deep-search evidence lifecycle smoke test using real MySQL and local fixtures.

This does not call a real literature MCP. It verifies the PTAgent durable path:

    hypothesis annotations -> fixture literature records -> evidence ledger
    -> verdict history references -> frozen manifest -> report artifact

The four fixture diseases cover support, refute, conflicting, and insufficient
verdicts. Their contents are test data, not biological conclusions.
"""

from __future__ import annotations

import argparse
import os
import sys
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

from application.experiment import freeze_experiment  # noqa: E402
from application.knowledge import verify_experiment_hypotheses  # noqa: E402
from application.report import (  # noqa: E402
    generate_experiment_report,
    persist_experiment_report,
)
from pkg.deep_search import (  # noqa: E402
    EvidenceRecord,
    EvidenceStance,
    InMemoryLiteratureSource,
)
from pkg.experiment import (  # noqa: E402
    AnnotationTargetType,
    EvidenceLevel,
    ExperimentBundle,
    ExperimentContext,
    ExperimentGroup,
    GroupRole,
    MetaAnnotation,
    MySQLExperimentStore,
    ProteinRecord,
)


def _experiment_id() -> str:
    return "exp_deep_search_smoke_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _bundle(experiment_id: str) -> ExperimentBundle:
    return ExperimentBundle(
        context=ExperimentContext(
            experiment_id=experiment_id,
            session_id="deep_search_fixture_smoke",
            title="Deep-search evidence fixture MySQL smoke test",
            raw_text="Validate deep-search evidence persistence and frozen reporting.",
            disease=["Fixture disease set"],
            organism="Homo sapiens",
            taxon_id=9606,
            assay="fixture",
        ),
        groups=[
            ExperimentGroup(group_id="case", label="Case", role=GroupRole.CASE),
            ExperimentGroup(group_id="control", label="Control", role=GroupRole.CONTROL),
        ],
        proteins=[
            ProteinRecord(
                protein_id="prot_stat3",
                accession="P40763",
                gene="STAT3",
                organism="Homo sapiens",
                taxon_id=9606,
            )
        ],
        peptides=[],
    )


def _hypotheses(experiment_id: str) -> list[MetaAnnotation]:
    return [
        MetaAnnotation(
            annotation_id=f"ann_{disease_id.lower()}",
            experiment_id=experiment_id,
            target="prot_stat3",
            target_type=AnnotationTargetType.PROTEIN,
            attribute=f"disease:{disease_id}",
            value={"disease_id": disease_id, "disease_name": disease_name},
            evidence_level=EvidenceLevel.HYPOTHESIS,
            source="fixture-neighbor",
            derivation={"via_genes": ["STAT3"]},
        )
        for disease_id, disease_name in (
            ("D_SUPPORT", "Fixture supported disease"),
            ("D_REFUTE", "Fixture refuted disease"),
            ("D_CONFLICT", "Fixture conflicting disease"),
            ("D_EMPTY", "Fixture insufficient disease"),
        )
    ]


def _source() -> InMemoryLiteratureSource:
    return InMemoryLiteratureSource(
        by_disease={
            "D_SUPPORT": [
                EvidenceRecord(
                    EvidenceStance.SUPPORT,
                    "Fixture support paper",
                    "PMID:fixture-support",
                    "fixture-literature",
                    snippet="Fixture abstract fragment supporting the association.",
                    provenance={"fixture_case": "support"},
                )
            ],
            "D_REFUTE": [
                EvidenceRecord(
                    EvidenceStance.REFUTE,
                    "Fixture refute paper",
                    "PMID:fixture-refute",
                    "fixture-literature",
                    snippet="Fixture abstract fragment refuting the association.",
                    provenance={"fixture_case": "refute"},
                )
            ],
            "D_CONFLICT": [
                EvidenceRecord(
                    EvidenceStance.SUPPORT,
                    "Fixture conflict support paper",
                    "PMID:fixture-conflict-support",
                    "fixture-literature",
                    provenance={"fixture_case": "conflicting"},
                ),
                EvidenceRecord(
                    EvidenceStance.REFUTE,
                    "Fixture conflict refute paper",
                    "PMID:fixture-conflict-refute",
                    "fixture-literature",
                    provenance={"fixture_case": "conflicting"},
                ),
            ],
        }
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-id", default="", help="Optional fixed experiment ID.")
    parser.add_argument("--snapshot-version", default="1.0")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    experiment_id = args.experiment_id or _experiment_id()
    if len(experiment_id) > _EXPERIMENT_ID_MAX_LENGTH:
        raise SystemExit(
            f"experiment_id must be at most {_EXPERIMENT_ID_MAX_LENGTH} characters"
        )

    store = MySQLExperimentStore.from_settings()
    store.initialize_schema()
    store.save_bundle(_bundle(experiment_id))
    store.add_annotations(_hypotheses(experiment_id))

    summary = verify_experiment_hypotheses(
        experiment_id,
        repository=store,
        source=_source(),
    )
    snapshot = freeze_experiment(
        experiment_id,
        snapshot_version=args.snapshot_version,
        pipeline_version="deep-search-fixture-mysql-smoke",
        repository=store,
    )
    report = persist_experiment_report(
        generate_experiment_report(
            experiment_id,
            args.snapshot_version,
            repository=store,
        ),
        repository=store,
    )

    evidence = store.list_deep_search_evidence(experiment_id)
    history = store.list_annotation_history(experiment_id)

    print("experiment_id:", experiment_id)
    print("deep_search_summary:", summary)
    print("deep_search_evidence:", len(evidence))
    print("annotation_history:", len(history))
    print("snapshot_evidence_count:", snapshot.manifest["counts"]["deep_search_evidence"])
    print("snapshot_evidence_by_stance:", snapshot.manifest["deep_search"]["evidence_by_stance"])
    print("report_sections:", list(report.sections))
    print("report_has_evidence_section:", "8. Deep-search 证据明细（冻结快照）" in report.content)

    for row in evidence:
        print(
            "evidence_preview:",
            row.annotation_id,
            row.stance,
            row.reference,
            row.evidence_id,
        )
    for row in history:
        print(
            "history_preview:",
            row.annotation_id,
            row.verdict,
            row.evidence_ref.get("evidence_ids", []),
        )

    if len(evidence) != 4:
        raise SystemExit("expected four persisted fixture evidence rows")
    if snapshot.manifest["counts"]["deep_search_evidence"] != 4:
        raise SystemExit("frozen snapshot did not include all deep-search evidence")
    if "8. Deep-search 证据明细（冻结快照）" not in report.content:
        raise SystemExit("report is missing the frozen deep-search evidence section")


if __name__ == "__main__":
    main()
