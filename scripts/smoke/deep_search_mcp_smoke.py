"""Read-only smoke test for the configured real literature MCP source.

It calls the configured PTAGENT_DEEP_SEARCH MCP tool and validates that its
response can be normalized into EvidenceRecord values. It does not write MySQL,
change annotations, freeze an experiment, or generate a report.
"""

from __future__ import annotations

import argparse
import os
import sys
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

from config import get_settings  # noqa: E402
from pkg.deep_search import (  # noqa: E402
    DeepSearchTask,
    LiteratureMCPError,
    get_literature_search_source,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--query",
        default="STAT3 lupus nephritis Homo sapiens",
        help="Fallback query for generic_mcp; PubMed derives a Boolean query from gene/disease/organism.",
    )
    parser.add_argument("--gene", default="STAT3")
    parser.add_argument("--disease-id", default="MESH:D008181")
    parser.add_argument("--disease-name", default="Lupus Nephritis")
    parser.add_argument("--organism", default="Homo sapiens")
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Do not fail when the real MCP returns zero literature records.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    query = args.query.strip()
    if not query:
        raise SystemExit("--query must be non-empty")

    settings = get_settings().deep_search
    task = DeepSearchTask(
        annotation_id="ann_deep_search_mcp_smoke",
        experiment_id="exp_deep_search_mcp_smoke",
        protein_id="prot_stat3",
        gene=args.gene,
        disease_id=args.disease_id,
        disease_name=args.disease_name,
        organism=args.organism,
        query=query,
    )
    source = get_literature_search_source()
    try:
        evidence = source.search(task)
    except LiteratureMCPError as exc:
        raise SystemExit(f"real literature MCP smoke failed: {exc}") from exc

    by_stance = {
        stance: sum(1 for row in evidence if row.stance.value == stance)
        for stance in ("support", "refute", "neutral")
    }
    print("literature_mcp_endpoint:", settings.literature_mcp_endpoint)
    print("provider:", settings.provider)
    print("mcp_tool:", settings.mcp_tool)
    print("task_query:", query)
    if evidence:
        print("executed_query:", evidence[0].provenance.get("query", query))
    print("source:", source.name)
    print("source_version:", source.version)
    print("evidence_records:", len(evidence))
    print("evidence_by_stance:", by_stance)
    for index, row in enumerate(evidence, start=1):
        print(
            "evidence_preview:",
            index,
            row.stance.value,
            row.reference,
            row.source,
            row.title,
        )

    if not evidence and not args.allow_empty:
        raise SystemExit(
            "real literature MCP returned no records; rerun with a different query "
            "or pass --allow-empty when validating only connectivity"
        )


if __name__ == "__main__":
    main()
