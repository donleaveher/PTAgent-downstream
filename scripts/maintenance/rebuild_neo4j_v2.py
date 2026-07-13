"""Dry-run-first rebuild of Neo4j schema v2 from MySQL experiment facts.

MySQL remains the source of truth.  The default mode builds each requested
projection in memory and prints its deterministic manifest checksum.  Writing
Neo4j requires ``--apply``; clearing the existing graph additionally requires
the exact confirmation token ``RESET_NEO4J_V2``.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env", override=False)

from application.graph.project_kg import project_experiment_kg  # noqa: E402
from config.graph_settings import get_graph_settings  # noqa: E402
from pkg.experiment import MySQLExperimentStore  # noqa: E402
from pkg.graph import InMemoryGraphStore, Neo4jGraphStore  # noqa: E402

_RESET_TOKEN = "RESET_NEO4J_V2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--experiment-id",
        action="append",
        required=True,
        help="MySQL experiment to rebuild; repeat for multiple experiments.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the computed schema-v2 projections to Neo4j.",
    )
    parser.add_argument(
        "--reset-graph",
        action="store_true",
        help="Delete the entire Neo4j graph before applying the requested projections.",
    )
    parser.add_argument(
        "--confirm-reset",
        default="",
        metavar="TOKEN",
        help=f"Required with --reset-graph; must equal {_RESET_TOKEN}.",
    )
    return parser.parse_args()


def _manifest_line(experiment_id: str, summary: dict[str, object]) -> str:
    manifest = summary["manifest"]
    assert isinstance(manifest, dict)
    return (
        f"experiment={experiment_id} schema={manifest['schema_version']} "
        f"nodes={len(manifest['node_records'])} edges={len(manifest['edge_records'])} "
        f"checksum={manifest['checksum']}"
    )


def _frozen_graph_checksum(
    repository: MySQLExperimentStore, experiment_id: str
) -> str | None:
    snapshots = repository.list_snapshots(experiment_id)
    if not snapshots:
        return None
    graph = snapshots[-1].manifest.get("graph") or {}
    checksum = graph.get("checksum")
    return str(checksum) if checksum else None


def main() -> None:
    args = parse_args()
    if args.reset_graph and not args.apply:
        raise SystemExit("--reset-graph requires --apply")
    if args.reset_graph and args.confirm_reset != _RESET_TOKEN:
        raise SystemExit(
            f"--reset-graph requires --confirm-reset {_RESET_TOKEN}"
        )

    experiment_ids = list(dict.fromkeys(args.experiment_id))
    repository = MySQLExperimentStore.from_settings()
    repository.initialize_schema()

    previews: dict[str, dict[str, object]] = {}
    for experiment_id in experiment_ids:
        if repository.get_context(experiment_id) is None:
            raise SystemExit(f"unknown MySQL experiment: {experiment_id}")
        previews[experiment_id] = project_experiment_kg(
            experiment_id,
            repository=repository,
            store=InMemoryGraphStore(),
        )

    print("mode:", "apply" if args.apply else "dry-run")
    print("reset_graph:", args.reset_graph)
    for experiment_id, summary in previews.items():
        print("plan:", _manifest_line(experiment_id, summary))
        manifest = summary["manifest"]
        assert isinstance(manifest, dict)
        frozen_checksum = _frozen_graph_checksum(repository, experiment_id)
        print("frozen_graph_checksum:", frozen_checksum or "not-available")
        print(
            "frozen_graph_matches:",
            frozen_checksum == manifest["checksum"] if frozen_checksum else "not-available",
        )
    if not args.apply:
        print("neo4j_changed: False")
        return

    settings = get_graph_settings()
    graph = Neo4jGraphStore(
        settings.uri,
        settings.user,
        settings.password,
        settings.database,
        connection_timeout=settings.connection_timeout_seconds,
        max_connection_lifetime=settings.max_connection_lifetime_seconds,
        max_transaction_retry_time=settings.max_transaction_retry_seconds,
    )
    try:
        if args.reset_graph:
            result = graph.run(
                "MATCH (n) WITH collect(n) AS nodes "
                "FOREACH (n IN nodes | DETACH DELETE n) "
                "RETURN size(nodes) AS deleted"
            )
            print("reset_deleted_nodes:", result[0]["deleted"] if result else 0)
        graph.initialize_schema()
        for experiment_id in experiment_ids:
            summary = project_experiment_kg(
                experiment_id,
                repository=repository,
                store=graph,
            )
            expected = previews[experiment_id]["manifest"]
            actual = summary["manifest"]
            if actual != expected:
                raise RuntimeError(
                    f"projection manifest changed between preview and apply: {experiment_id}"
                )
            print("applied:", _manifest_line(experiment_id, summary))
        print("neo4j_changed: True")
    finally:
        graph.close()


if __name__ == "__main__":
    main()
