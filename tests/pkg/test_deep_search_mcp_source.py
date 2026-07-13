"""真实文献 MCP 适配器：调用参数、返回归一、失败语义与重试。"""

from __future__ import annotations

from time import sleep
from types import SimpleNamespace
from typing import Any

import pytest

from config.deep_search_settings import DeepSearchSettings
from pkg.deep_search import (
    DeepSearchTask,
    EvidenceStance,
    LiteratureMCPError,
    MCPLiteratureSearchSource,
    PubMedLiteratureSearchSource,
    get_literature_search_source,
    parse_literature_mcp_result,
)


def _task(*, candidate_genes: tuple[str, ...] = ()) -> DeepSearchTask:
    return DeepSearchTask(
        annotation_id="ann_1",
        experiment_id="exp_1",
        protein_id="prot_1",
        gene="STAT3",
        disease_id="MESH:D001",
        disease_name="Fixture disease",
        organism="Homo sapiens",
        query="STAT3 | Fixture disease | Homo sapiens",
        candidate_genes=candidate_genes,
    )


class _Client:
    def __init__(self, responses: list[dict[str, Any] | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_mcp_source_normalizes_explicit_stances_and_versions() -> None:
    client = _Client(
        [
            {
                "version": "deepxiv-2026.07",
                "results": [
                    {
                        "title": "Supporting paper",
                        "pmid": "123",
                        "source": "PubMed",
                        "stance": "supported",
                        "abstract": "x" * 30,
                        "score": 0.91,
                    },
                    {
                        "title": "Refuting paper",
                        "doi": "10.1000/example",
                        "source": "Crossref",
                        "stance": "refute",
                    },
                ],
            }
        ]
    )
    source = MCPLiteratureSearchSource(
        client,
        tool_name="deepxiv_search",
        max_results=3,
        max_snippet_chars=12,
        version="configured-v1",
    )

    evidence = source.search(_task())

    assert client.calls == [
        (
            "deepxiv_search",
            {"query": "STAT3 | Fixture disease | Homo sapiens", "top_k": 3},
        )
    ]
    assert source.version == "deepxiv-2026.07"
    assert [(row.stance, row.reference, row.source) for row in evidence] == [
        (EvidenceStance.SUPPORT, "PMID:123", "PubMed"),
        (EvidenceStance.REFUTE, "DOI:10.1000/example", "Crossref"),
    ]
    assert evidence[0].snippet == "x" * 12
    assert evidence[0].provenance["mcp_tool"] == "deepxiv_search"
    assert evidence[0].provenance["score"] == 0.91


def test_missing_stance_is_neutral_and_keeps_configured_version() -> None:
    version, evidence = parse_literature_mcp_result(
        {
            "items": [
                {
                    "title": "Unclassified literature result",
                    "url": "https://example.test/paper",
                }
            ]
        },
        tool_name="deepxiv_search",
        default_version="configured-v1",
    )

    assert version == "configured-v1"
    assert evidence[0].stance is EvidenceStance.NEUTRAL
    assert evidence[0].reference == "https://example.test/paper"


def test_malformed_non_empty_result_fails_closed() -> None:
    with pytest.raises(LiteratureMCPError, match="title and reference"):
        parse_literature_mcp_result(
            {"results": [{"title": "Missing citation"}]},
            tool_name="deepxiv_search",
        )

    with pytest.raises(LiteratureMCPError, match="no supported result list"):
        parse_literature_mcp_result({"status": "ok"}, tool_name="deepxiv_search")


def test_source_retries_transient_call_failure() -> None:
    client = _Client(
        [
            RuntimeError("temporary broker failure"),
            {
                "results": [
                    {
                        "title": "Recovered response",
                        "reference": "PMID:42",
                    }
                ]
            },
        ]
    )
    source = MCPLiteratureSearchSource(
        client,
        max_attempts=2,
        retry_backoff_seconds=0,
        version="configured-v1",
    )

    evidence = source.search(_task())

    assert len(client.calls) == 2
    assert evidence[0].stance is EvidenceStance.NEUTRAL


def test_source_times_out_and_reports_final_attempt() -> None:
    class _SlowClient:
        def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
            sleep(0.05)
            return {"results": []}

    source = MCPLiteratureSearchSource(
        _SlowClient(),
        timeout_seconds=0.001,
        max_attempts=1,
        retry_backoff_seconds=0,
    )
    with pytest.raises(LiteratureMCPError, match="failed after 1 attempt"):
        source.search(_task())


def test_pubmed_source_searches_then_fetches_articles() -> None:
    client = _Client(
        [
            {"pmids": ["101", "202"], "summaries": []},
            {
                "articles": [
                    {
                        "pmid": "101",
                        "title": "STAT3 in disease",
                        "abstractText": "A" * 30,
                        "doi": "10.1/example",
                        "pmcId": "PMC101",
                        "pubmedUrl": "https://pubmed.example/101",
                        "journalInfo": {"title": "Journal X"},
                        "publicationTypes": ["Review"],
                        "meshTerms": [{"descriptorName": "STAT3"}],
                    },
                    {
                        "pmid": "202",
                        "title": "Independent evidence",
                        "abstractText": "B",
                    },
                ]
            },
        ]
    )
    source = PubMedLiteratureSearchSource(
        client,
        max_results=2,
        max_snippet_chars=12,
        version="pubmed-mcp-v2.9.8",
    )

    evidence = source.search(_task())

    assert client.calls == [
        (
            "pubmed_search_articles",
            {
                "query": "(STAT3) AND (Fixture disease) AND (Homo sapiens)",
                "maxResults": 2,
                "summaryCount": 2,
                "hasAbstract": True,
            },
        ),
        (
            "pubmed_fetch_articles",
            {
                "pmids": ["101", "202"],
                "includeMesh": True,
                "includeGrants": False,
            },
        ),
    ]
    assert [(row.reference, row.stance) for row in evidence] == [
        ("PMID:101", EvidenceStance.NEUTRAL),
        ("PMID:202", EvidenceStance.NEUTRAL),
    ]
    assert evidence[0].snippet == "A" * 12
    assert evidence[0].provenance["mesh_terms"] == ["STAT3"]
    assert evidence[0].provenance["journal"] == "Journal X"
    assert evidence[0].provenance["query"] == "(STAT3) AND (Fixture disease) AND (Homo sapiens)"
    assert evidence[0].provenance["query_scope"] == "primary"
    assert source.version == "pubmed-mcp-v2.9.8"


def test_pubmed_source_uses_candidate_gene_only_after_primary_zero_results() -> None:
    client = _Client(
        [
            {"pmids": []},
            {"pmids": ["303"]},
            {
                "articles": [
                    {
                        "pmid": "303",
                        "title": "JAK1 fallback literature",
                        "abstractText": "Fallback result.",
                    }
                ]
            },
        ]
    )
    source = PubMedLiteratureSearchSource(
        client,
        max_results=2,
        retry_backoff_seconds=0,
        candidate_fallback_max_queries=2,
    )

    evidence = source.search(_task(candidate_genes=("JAK1", "STAT3")))

    assert client.calls == [
        (
            "pubmed_search_articles",
            {
                "query": "(STAT3) AND (Fixture disease) AND (Homo sapiens)",
                "maxResults": 2,
                "summaryCount": 2,
                "hasAbstract": True,
            },
        ),
        (
            "pubmed_search_articles",
            {
                "query": "(JAK1) AND (Fixture disease)",
                "maxResults": 2,
                "summaryCount": 2,
                "hasAbstract": True,
            },
        ),
        (
            "pubmed_fetch_articles",
            {
                "pmids": ["303"],
                "includeMesh": True,
                "includeGrants": False,
            },
        ),
    ]
    assert evidence[0].reference == "PMID:303"
    assert evidence[0].stance is EvidenceStance.NEUTRAL
    assert evidence[0].provenance["query_scope"] == "candidate_fallback"
    assert evidence[0].provenance["candidate_gene"] == "JAK1"
    assert evidence[0].provenance["primary_query"] == (
        "(STAT3) AND (Fixture disease) AND (Homo sapiens)"
    )


def test_pubmed_source_does_not_query_candidates_when_primary_has_results() -> None:
    client = _Client(
        [
            {"pmids": ["101"]},
            {"articles": [{"pmid": "101", "title": "Primary literature"}]},
        ]
    )
    source = PubMedLiteratureSearchSource(client, retry_backoff_seconds=0)

    evidence = source.search(_task(candidate_genes=("JAK1",)))

    assert len(client.calls) == 2
    assert evidence[0].provenance["query_scope"] == "primary"


def test_pubmed_source_rejects_empty_fetch_after_non_empty_search() -> None:
    source = PubMedLiteratureSearchSource(
        _Client([{"pmids": ["101"]}, {"articles": []}]),
        retry_backoff_seconds=0,
    )
    with pytest.raises(LiteratureMCPError, match="returned no articles"):
        source.search(_task())


def test_factory_uses_deep_search_and_mcp_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    import config
    import pkg.mcp.client_pool as client_pool

    client = _Client([])
    settings = DeepSearchSettings(
        provider="generic_mcp",
        literature_mcp_endpoint="http://mcp.test/mcp",
        mcp_tool="literature_tool",
        query_argument="q",
        limit_argument="limit",
        max_results=7,
        timeout_seconds=11,
        max_attempts=3,
        retry_backoff_seconds=0,
        source_version="tool-v1",
        default_stance="neutral",
    )
    monkeypatch.setattr(
        config,
        "get_settings",
        lambda: SimpleNamespace(deep_search=settings),
    )
    monkeypatch.setattr(client_pool, "get_mcp_client", lambda endpoint: client)

    source = get_literature_search_source()

    assert isinstance(source, MCPLiteratureSearchSource)
    assert source.tool_name == "literature_tool"
    assert source.query_argument == "q"
    assert source.limit_argument == "limit"
    assert source.max_results == 7
    assert source.version == "tool-v1"
