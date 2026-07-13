"""Persist a controlled real-PubMed retrieval through the deep-search lifecycle.

This script creates a timestamped, clearly labeled test experiment for a
gene-disease hypothesis, retrieves live PubMed records through the local MCP,
and persists its evidence ledger, verdict history, frozen snapshot, and report.
It never represents its test hypothesis or retrieved records as a conclusion.
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
from pkg.deep_search import EvidenceStance, get_literature_search_source  # noqa: E402
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
    return "exp_real_pubmed_smoke_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def _bundle(experiment_id: str, *, gene: str, organism: str) -> ExperimentBundle:
    return ExperimentBundle(
        context=ExperimentContext(
            experiment_id=experiment_id,
            session_id="real_pubmed_smoke",
            title=f"Real PubMed persistence smoke: {gene}",
            raw_text=(
                "Controlled test experiment for real PubMed retrieval and persistence; "
                "not a biological conclusion."
            ),
            disease=["Lupus Nephritis"],
            organism=organism,
            taxon_id=9606 if organism == "Homo sapiens" else None,
            assay="real-pubmed-smoke",
        ),
        groups=[
            ExperimentGroup(group_id="case", label="Case", role=GroupRole.CASE),
            ExperimentGroup(group_id="control", label="Control", role=GroupRole.CONTROL),
        ],
        proteins=[
            ProteinRecord(
                protein_id=f"prot_{gene.lower()}",
                accession="P40763" if gene == "STAT3" else f"SMOKE_{gene}",
                gene=gene,
                organism=organism,
                taxon_id=9606 if organism == "Homo sapiens" else None,
            )
        ],
        peptides=[],
    )


def _hypothesis(
    experiment_id: str,
    *,
    gene: str,
    disease_id: str,
    disease_name: str,
) -> MetaAnnotation:
    return MetaAnnotation(
        annotation_id="ann_real_pubmed_hypothesis",
        experiment_id=experiment_id,
        target=f"prot_{gene.lower()}",
        target_type=AnnotationTargetType.PROTEIN,
        attribute=f"disease:{disease_id}",
        value={"disease_id": disease_id, "disease_name": disease_name},
        evidence_level=EvidenceLevel.HYPOTHESIS,
        source="real-pubmed-smoke",
        derivation={"test_only": True, "via_genes": [gene]},
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-id", default="", help="Optional fixed experiment ID.")
    parser.add_argument("--snapshot-version", default="1.0")
    parser.add_argument("--gene", default="STAT3")
    parser.add_argument("--disease-id", default="MESH:D008181")
    parser.add_argument("--disease-name", default="Lupus Nephritis")
    parser.add_argument("--organism", default="Homo sapiens")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    experiment_id = args.experiment_id or _experiment_id()
    if len(experiment_id) > _EXPERIMENT_ID_MAX_LENGTH:
        raise SystemExit(
            f"experiment_id must be at most {_EXPERIMENT_ID_MAX_LENGTH} characters"
        )
    if not all(
        value.strip()
        for value in (args.gene, args.disease_id, args.disease_name, args.organism)
    ):
        raise SystemExit("gene, disease ID/name, and organism must be non-empty")

    source = get_literature_search_source()
    if source.name != "PubMed-MCP":
        raise SystemExit(f"expected PubMed-MCP source, received {source.name!r}")

    store = MySQLExperimentStore.from_settings()
    store.initialize_schema()
    store.save_bundle(_bundle(experiment_id, gene=args.gene, organism=args.organism))
    store.add_annotations(
        [
            _hypothesis(
                experiment_id,
                gene=args.gene,
                disease_id=args.disease_id,
                disease_name=args.disease_name,
            )
        ]
    )

    summary = verify_experiment_hypotheses(
        experiment_id,
        repository=store,
        source=source,
    )
    evidence = store.list_deep_search_evidence(experiment_id)
    history = store.list_annotation_history(experiment_id)
    if not evidence:
        raise SystemExit("real PubMed returned no evidence; test experiment was retained")
    if any(row.stance != EvidenceStance.NEUTRAL.value for row in evidence):
        raise SystemExit("PubMed smoke expected neutral retrieval evidence only")
    if summary["verdicts"]["insufficient"] != 1:
        raise SystemExit("neutral PubMed evidence must leave the hypothesis insufficient")

    snapshot = freeze_experiment(
        experiment_id,
        snapshot_version=args.snapshot_version,
        pipeline_version="real-pubmed-mysql-smoke",
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

    print("experiment_id:", experiment_id)
    print("source:", source.name)
    print("source_version:", source.version)
    print("deep_search_summary:", summary)
    print("deep_search_evidence:", len(evidence))
    print("annotation_history:", len(history))
    print("snapshot_evidence_count:", snapshot.manifest["counts"]["deep_search_evidence"])
    print("report_has_evidence_section:", "8. Deep-search 证据明细（冻结快照）" in report.content)
    for row in evidence:
        print("evidence_preview:", row.stance, row.reference, row.title)

    if snapshot.manifest["counts"]["deep_search_evidence"] != len(evidence):
        raise SystemExit("frozen snapshot did not include all persisted PubMed evidence")
    if "8. Deep-search 证据明细（冻结快照）" not in report.content:
        raise SystemExit("report is missing the frozen deep-search evidence section")


if __name__ == "__main__":
    main()
