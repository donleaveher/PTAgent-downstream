"""UniProt MCP gene 解析：accession → gene symbol（M3 借 CTD 的桥）。"""

from __future__ import annotations

from typing import Any

from pkg.annotation import UniProtMCPGeneResolver, parse_uniprot_gene_map


def test_parse_gene_from_results_list() -> None:
    raw = {"results": [{"primaryAccession": "P12345", "primaryGeneName": "Jak2"}]}
    assert parse_uniprot_gene_map(raw) == {"P12345": "Jak2"}


def test_parse_gene_from_nested_genes_field() -> None:
    raw = {"data": {"Q99999": {"genes": [{"geneName": {"value": "STAT3"}}]}}}
    assert parse_uniprot_gene_map(raw) == {"Q99999": "STAT3"}


def test_parse_gene_semicolon_takes_first() -> None:
    raw = {"data": {"accession": "P1", "gene": "AAA;BBB"}}
    assert parse_uniprot_gene_map(raw) == {"P1": "AAA"}


def test_parse_skips_records_without_gene() -> None:
    raw = {"results": [{"accession": "P1"}, {"accession": "P2", "geneName": "G2"}]}
    assert parse_uniprot_gene_map(raw) == {"P2": "G2"}


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        return {
            "results": [
                {"accession": acc, "geneName": f"G_{acc}"} for acc in arguments["accessions"]
            ]
        }


def test_resolver_dedups_and_batches() -> None:
    client = _FakeClient()
    resolver = UniProtMCPGeneResolver(
        client, tool_name="uniprot_annot", accessions_argument="accessions", batch_size=2
    )
    out = resolver.resolve(["P3", "P1", "P2", "P1"])
    assert [call[1]["accessions"] for call in client.calls] == [["P1", "P2"], ["P3"]]
    assert out == {"P1": "G_P1", "P2": "G_P2", "P3": "G_P3"}
