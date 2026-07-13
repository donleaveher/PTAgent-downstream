from __future__ import annotations

from application.graph.gnn_export import build_gnn_export


def test_gnn_export_is_deterministic_and_indexes_edge_endpoints() -> None:
    manifest = {
        "schema_version": "2",
        "node_records": [
            {"label": "Gene", "key": "G1", "scope": "GENERAL", "properties": {}},
            {"label": "Protein", "key": "P1", "scope": "GENERAL", "properties": {}},
        ],
        "edge_records": [
            {
                "type": "ENCODED_BY",
                "key": "e1",
                "scope": "GENERAL",
                "start": {"label": "Protein", "key": "P1"},
                "end": {"label": "Gene", "key": "G1"},
                "properties": {},
            }
        ],
    }

    first = build_gnn_export(manifest)
    second = build_gnn_export(manifest)

    assert first == second
    assert first["node_table"][0]["key"] == "G1"
    assert first["edge_index"][0]["source"] == 1
    assert first["edge_index"][0]["target"] == 0
