"""Deterministic GNN-oriented export from a frozen graph manifest."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def build_gnn_export(graph_manifest: dict[str, Any]) -> dict[str, Any]:
    nodes = list(graph_manifest.get("node_records") or [])
    edges = list(graph_manifest.get("edge_records") or [])
    ordered_nodes = sorted(nodes, key=lambda row: (row["label"], row["key"]))
    index_by_node = {
        (row["label"], row["key"]): index
        for index, row in enumerate(ordered_nodes)
    }
    node_table = [
        {
            "index": index,
            "label": row["label"],
            "key": row["key"],
            "scope": row["scope"],
            "features": row.get("properties") or {},
        }
        for index, row in enumerate(ordered_nodes)
    ]
    edge_index = [
        {
            "source": index_by_node[(row["start"]["label"], row["start"]["key"])],
            "target": index_by_node[(row["end"]["label"], row["end"]["key"])],
            "type": row["type"],
            "key": row["key"],
            "scope": row["scope"],
            "features": row.get("properties") or {},
        }
        for row in sorted(edges, key=lambda item: (item["type"], item["key"]))
    ]
    payload = {
        "schema_version": str(graph_manifest.get("schema_version") or ""),
        "node_table": node_table,
        "edge_index": edge_index,
        "node_labels": sorted({row["label"] for row in node_table}),
        "edge_types": sorted({row["type"] for row in edge_index}),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return {
        **payload,
        "checksum": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }


__all__ = ["build_gnn_export"]
