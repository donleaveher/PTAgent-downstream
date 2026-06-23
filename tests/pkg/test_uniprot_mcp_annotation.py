"""UniProt MCP 返回归一与批量调用。"""

from __future__ import annotations

from typing import Any

from pkg.annotation import UniProtMCPAnnotationSource, parse_uniprot_mcp_result


def test_parse_normalized_and_aggregate_facts() -> None:
    raw = {
        "dbVersion": "2026_02",
        "results": [
            {
                "primaryAccession": "P12345",
                "domains": ["SH2", "JH1"],
                "tissues": "brain;liver",
                "organism": "Rattus norvegicus",
                "annotations": [
                    {
                        "attribute": "go",
                        "value": "GO:0007165",
                        "evidenceCode": "ECO:0000269",
                        "ref": "UniProt:P12345",
                    }
                ],
            }
        ],
    }
    version, parsed = parse_uniprot_mcp_result(
        raw,
        tool_name="protein_annot",
        default_version="unknown",
    )
    assert version == "2026_02"
    facts = parsed["P12345"]
    assert {(f.attribute, f.value) for f in facts} >= {
        ("domain", "SH2"),
        ("domain", "JH1"),
        ("tissue", "brain"),
        ("tissue", "liver"),
        ("organism", "Rattus norvegicus"),
        ("go", "GO:0007165"),
    }
    go = next(f for f in facts if f.attribute == "go")
    assert go.evidence_code == "ECO:0000269"
    assert go.source_ref == "UniProt:P12345"
    assert go.provenance["db_version"] == "2026_02"


def test_parse_accession_keyed_mapping() -> None:
    _, parsed = parse_uniprot_mcp_result(
        {"data": {"Q99999": {"go_terms": ["GO:1"], "taxonId": 9606}}},
        tool_name="protein_annot",
        default_version="v1",
    )
    assert {(f.attribute, f.value) for f in parsed["Q99999"]} == {
        ("go", "GO:1"),
        ("taxon_id", 9606),
    }


def test_parse_single_data_record() -> None:
    _, parsed = parse_uniprot_mcp_result(
        {"data": {"accession": "P1", "ecNumbers": ["2.7.11.1"]}},
        tool_name="protein_annot",
        default_version="v1",
    )
    assert [(f.attribute, f.value) for f in parsed["P1"]] == [("ec", "2.7.11.1")]


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        return {
            "version": "2026_03",
            "results": [
                {"accession": accession, "domains": [f"D-{accession}"]}
                for accession in arguments["ids"]
            ],
        }


def test_source_deduplicates_and_batches_accessions() -> None:
    client = _FakeClient()
    source = UniProtMCPAnnotationSource(
        client,
        tool_name="protein_annot",
        accessions_argument="ids",
        batch_size=2,
    )
    result = source.fetch(["P3", "P1", "P2", "P1"])
    assert [call[1]["ids"] for call in client.calls] == [["P1", "P2"], ["P3"]]
    assert set(result) == {"P1", "P2", "P3"}
    assert source.version == "2026_03"
