"""Read-only protocol smoke test for the locally hosted PubMed MCP service.

The test verifies the MCP connection, required tool registration, and the real
``pubmed_search_articles`` -> ``pubmed_fetch_articles`` flow.  It does not
write to MySQL, mutate experiments, or invoke PTAgent's verdict logic.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENDPOINT = "http://127.0.0.1:3010/mcp"
REQUIRED_TOOLS = {"pubmed_search_articles", "pubmed_fetch_articles"}


def _load_environment() -> None:
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:  # pragma: no cover - local setup issue only
        return
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint",
        default=os.environ.get(
            "PTAGENT_DEEP_SEARCH__LITERATURE_MCP_ENDPOINT", DEFAULT_ENDPOINT
        ),
        help="Streamable HTTP MCP endpoint (default: %(default)s).",
    )
    parser.add_argument(
        "--query",
        default="STAT3 lupus nephritis Homo sapiens",
        help="PubMed query sent to pubmed_search_articles.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=3,
        help="Number of PMIDs to search and fetch (1-10; default: %(default)s).",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Treat a successful zero-result search as a connectivity-only pass.",
    )
    return parser.parse_args()


def _pmids(raw: dict[str, Any]) -> list[str]:
    value = raw.get("pmids")
    if not isinstance(value, list) or not all(isinstance(pmid, str) for pmid in value):
        raise ValueError("pubmed_search_articles response has no string 'pmids' list")
    return list(dict.fromkeys(pmid.strip() for pmid in value if pmid.strip()))


def _articles(raw: dict[str, Any], searched_pmids: set[str]) -> list[dict[str, Any]]:
    value = raw.get("articles")
    if not isinstance(value, list) or not all(isinstance(article, dict) for article in value):
        raise ValueError("pubmed_fetch_articles response has no object 'articles' list")

    valid: list[dict[str, Any]] = []
    for index, article in enumerate(value, start=1):
        pmid = article.get("pmid")
        title = article.get("title")
        if not isinstance(pmid, str) or not pmid.strip():
            raise ValueError(f"fetched article #{index} has no PMID")
        if pmid not in searched_pmids:
            raise ValueError(f"fetched article #{index} returned unrequested PMID {pmid!r}")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"fetched article #{index} has no title")
        valid.append(article)
    return valid


def main() -> None:
    _load_environment()
    args = parse_args()
    endpoint = args.endpoint.strip()
    query = args.query.strip()
    if not endpoint:
        raise SystemExit("PubMed MCP smoke failed: --endpoint must be non-empty")
    if not query:
        raise SystemExit("PubMed MCP smoke failed: --query must be non-empty")
    if not 1 <= args.max_results <= 10:
        raise SystemExit("PubMed MCP smoke failed: --max-results must be between 1 and 10")

    os.chdir(PROJECT_ROOT)
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from pkg.mcp.client import MCPClient  # noqa: PLC0415
    from pkg.mcp.errors import MCPError  # noqa: PLC0415

    client = MCPClient(endpoint)
    try:
        tool_names = {tool.name for tool in client.list_tools()}
        missing_tools = sorted(REQUIRED_TOOLS - tool_names)
        if missing_tools:
            raise ValueError(f"MCP endpoint is missing required tools: {', '.join(missing_tools)}")

        search_result = client.call_tool(
            "pubmed_search_articles",
            {
                "query": query,
                "maxResults": args.max_results,
                "summaryCount": args.max_results,
                "hasAbstract": True,
            },
        )
        pmids = _pmids(search_result)
        if not pmids:
            if args.allow_empty:
                print("PubMed MCP smoke passed: connected and required tools are available; search returned 0 PMIDs.")
                return
            raise ValueError("search returned 0 PMIDs; retry with --query or use --allow-empty")

        fetch_result = client.call_tool(
            "pubmed_fetch_articles",
            {"pmids": pmids, "includeMesh": True, "includeGrants": False},
        )
        articles = _articles(fetch_result, set(pmids))
        if not articles:
            raise ValueError("fetch returned 0 articles for non-empty search PMIDs")
    except (MCPError, ValueError) as exc:
        raise SystemExit(f"PubMed MCP smoke failed: {exc}") from exc

    print("PubMed MCP smoke passed")
    print("endpoint:", endpoint)
    print("query:", query)
    print("available_tools:", len(tool_names))
    print("searched_pmids:", len(pmids))
    print("fetched_articles:", len(articles))
    for index, article in enumerate(articles, start=1):
        mesh_terms = article.get("meshTerms")
        mesh_count = len(mesh_terms) if isinstance(mesh_terms, list) else 0
        print(
            "article_preview:",
            index,
            article["pmid"],
            f"mesh_terms={mesh_count}",
            article["title"],
        )


if __name__ == "__main__":
    main()
