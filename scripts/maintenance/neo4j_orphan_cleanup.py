"""Dry-run-first cleanup for orphaned Neo4j smoke fixture nodes."""

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

from config.graph_settings import get_graph_settings  # noqa: E402
from pkg.graph import Neo4jGraphStore  # noqa: E402

_MATCH = """
MATCH (n {scope: 'GENERAL'})
WHERE NOT (n)--()
  AND (n.key STARTS WITH 'NEOSMOKE_' OR n.key STARTS WITH 'SMOKE:')
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete the listed smoke fixture nodes; default is read-only dry-run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_graph_settings()
    graph = Neo4jGraphStore(
        settings.uri, settings.user, settings.password, settings.database
    )
    try:
        rows = graph.run(
            _MATCH
            + " RETURN labels(n)[0] AS label, n.key AS key ORDER BY label, key"
        )
        print("mode:", "apply" if args.apply else "dry-run")
        print("orphan_smoke_nodes:", len(rows))
        for row in rows:
            print("orphan:", row["label"], row["key"])
        if args.apply and rows:
            deleted = graph.run(
                _MATCH
                + " WITH collect(n) AS nodes FOREACH (n IN nodes | DELETE n) "
                "RETURN size(nodes) AS deleted"
            )
            print("deleted:", deleted[0]["deleted"] if deleted else 0)
    finally:
        graph.close()


if __name__ == "__main__":
    main()
