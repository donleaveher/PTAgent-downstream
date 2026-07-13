"""Deep-search 检索源：测试 fixture 与生产 MCP 文献适配器。"""

from __future__ import annotations

from queue import Empty, Queue
from threading import Event, Thread
from time import sleep
from typing import Any, Protocol

from pkg.deep_search.types import (
    DeepSearchTask,
    EvidenceRecord,
    EvidenceStance,
    LiteratureSearchSource,
)


class LiteratureMCPError(RuntimeError):
    """文献 MCP 不可用或返回契约不合法。"""


class ToolCaller(Protocol):
    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


_RESULT_KEYS = ("results", "data", "items", "hits", "result", "papers", "articles")
_TITLE_KEYS = ("title", "paper_title", "paperTitle", "name")
_SOURCE_KEYS = ("source", "source_name", "sourceName", "database", "provider")
_SNIPPET_KEYS = ("snippet", "abstract", "summary", "text", "content")
_VERSION_KEYS = ("source_version", "sourceVersion", "db_version", "dbVersion", "version")
_SUPPORT_STANCES = {
    "support",
    "supports",
    "supported",
    "supporting",
    "positive",
    "confirm",
    "confirmed",
}
_REFUTE_STANCES = {
    "refute",
    "refutes",
    "refuted",
    "negative",
    "contradict",
    "contradicts",
    "contradicted",
    "disprove",
    "disproves",
    "disproved",
}


def _first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return None


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _version(raw: dict[str, Any], fallback: str) -> str:
    metadata = raw.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    return _text(_first(raw, *_VERSION_KEYS) or _first(metadata, *_VERSION_KEYS)) or fallback


def _result_rows(raw: dict[str, Any]) -> list[dict[str, Any]]:
    for key in _RESULT_KEYS:
        if key not in raw:
            continue
        value = raw[key]
        if isinstance(value, list):
            if not all(isinstance(row, dict) for row in value):
                raise LiteratureMCPError(f"MCP result field {key!r} must contain objects")
            return list(value)
        if isinstance(value, dict):
            return [value]
        raise LiteratureMCPError(f"MCP result field {key!r} must be a list or object")
    if any(key in raw for key in _TITLE_KEYS):
        return [raw]
    raise LiteratureMCPError(
        "literature MCP result has no supported result list "
        f"(expected one of {', '.join(_RESULT_KEYS)})"
    )


def _reference(record: dict[str, Any]) -> str:
    direct = _text(_first(record, "reference", "citation", "cite"))
    if direct:
        return direct
    pmid = _text(_first(record, "pmid", "PMID", "pubmed_id", "pubmedId"))
    if pmid:
        return pmid if pmid.upper().startswith("PMID:") else f"PMID:{pmid}"
    doi = _text(_first(record, "doi", "DOI"))
    if doi:
        return doi if doi.upper().startswith("DOI:") else f"DOI:{doi}"
    return _text(_first(record, "url", "link", "paper_url", "paperUrl", "id"))


def _stance(record: dict[str, Any], default: EvidenceStance) -> EvidenceStance:
    value = _text(_first(record, "stance", "evidence_stance", "evidenceStance", "verdict"))
    normalized = value.lower().replace("-", "_").replace(" ", "_")
    if normalized in _SUPPORT_STANCES:
        return EvidenceStance.SUPPORT
    if normalized in _REFUTE_STANCES:
        return EvidenceStance.REFUTE
    if normalized == "neutral":
        return EvidenceStance.NEUTRAL
    if record.get("is_supporting") is True or record.get("isSupporting") is True:
        return EvidenceStance.SUPPORT
    if record.get("is_refuting") is True or record.get("isRefuting") is True:
        return EvidenceStance.REFUTE
    return default


def _provenance(record: dict[str, Any], *, tool_name: str, result_index: int) -> dict[str, Any]:
    out: dict[str, Any] = {"mcp_tool": tool_name, "result_index": result_index}
    for key in ("id", "pmid", "doi", "url", "year", "publication_date", "publicationDate", "score"):
        value = record.get(key)
        if isinstance(value, (str, int, float, bool)):
            out[key] = value
    return out


def parse_literature_mcp_result(
    raw: dict[str, Any],
    *,
    tool_name: str,
    default_stance: EvidenceStance = EvidenceStance.NEUTRAL,
    max_snippet_chars: int = 1000,
    default_version: str = "MCP-current",
) -> tuple[str, list[EvidenceRecord]]:
    """校验并归一常见文献 MCP 返回，不从文本内容推断证据立场。"""

    if not isinstance(raw, dict):
        raise LiteratureMCPError("literature MCP tool returned a non-object result")
    if max_snippet_chars < 0:
        raise ValueError("max_snippet_chars must be non-negative")

    version = _version(raw, default_version)
    evidence: list[EvidenceRecord] = []
    for index, record in enumerate(_result_rows(raw), start=1):
        title = _text(_first(record, *_TITLE_KEYS))
        reference = _reference(record)
        if not title or not reference:
            raise LiteratureMCPError(
                f"literature MCP result #{index} requires non-empty title and reference"
            )
        snippet = _text(_first(record, *_SNIPPET_KEYS))
        evidence.append(
            EvidenceRecord(
                stance=_stance(record, default_stance),
                title=title,
                reference=reference,
                source=_text(_first(record, *_SOURCE_KEYS)) or tool_name,
                snippet=snippet[:max_snippet_chars],
                provenance=_provenance(
                    record,
                    tool_name=tool_name,
                    result_index=index,
                ),
            )
        )
    return version, evidence


def _call_with_timeout(
    client: ToolCaller,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    queue: Queue[tuple[dict[str, Any] | None, Exception | None]] = Queue(maxsize=1)
    done = Event()

    def invoke() -> None:
        try:
            queue.put((client.call_tool(tool_name, arguments), None))
        except Exception as exc:  # noqa: BLE001
            queue.put((None, exc))
        finally:
            done.set()

    Thread(target=invoke, daemon=True, name="deep-search-mcp").start()
    if not done.wait(timeout_seconds):
        raise TimeoutError(
            f"literature MCP tool {tool_name!r} timed out after {timeout_seconds:g}s"
        )
    try:
        result, error = queue.get_nowait()
    except Empty as exc:  # pragma: no cover - defensive thread scheduling guard
        raise LiteratureMCPError("literature MCP invocation completed without a result") from exc
    if error is not None:
        raise error
    if not isinstance(result, dict):
        raise LiteratureMCPError("literature MCP tool returned a non-object result")
    return result


def _call_with_retries(
    client: ToolCaller,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    timeout_seconds: float,
    max_attempts: int,
    retry_backoff_seconds: float,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return _call_with_timeout(
                client,
                tool_name=tool_name,
                arguments=arguments,
                timeout_seconds=timeout_seconds,
            )
        except LiteratureMCPError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < max_attempts and retry_backoff_seconds:
                sleep(retry_backoff_seconds * attempt)
    raise LiteratureMCPError(
        f"literature MCP tool {tool_name!r} failed after "
        f"{max_attempts} attempt(s): {last_error}"
    ) from last_error


class MCPLiteratureSearchSource:
    """经现有 MCP Broker 调用真实文献检索工具的生产检索源。"""

    def __init__(
        self,
        client: ToolCaller,
        *,
        tool_name: str = "deepxiv_search",
        query_argument: str = "query",
        limit_argument: str = "top_k",
        max_results: int = 5,
        timeout_seconds: float = 20.0,
        max_attempts: int = 2,
        retry_backoff_seconds: float = 1.0,
        version: str = "MCP-current",
        default_stance: EvidenceStance = EvidenceStance.NEUTRAL,
        max_snippet_chars: int = 1000,
    ) -> None:
        if not tool_name or not query_argument or not limit_argument:
            raise ValueError("tool_name, query_argument, and limit_argument must be non-empty")
        if query_argument == limit_argument:
            raise ValueError("query_argument and limit_argument must differ")
        if max_results < 1 or timeout_seconds <= 0 or max_attempts < 1:
            raise ValueError("max_results, timeout_seconds, and max_attempts must be positive")
        if retry_backoff_seconds < 0 or max_snippet_chars < 0:
            raise ValueError("retry_backoff_seconds and max_snippet_chars must be non-negative")
        self._client = client
        self.tool_name = tool_name
        self.query_argument = query_argument
        self.limit_argument = limit_argument
        self.max_results = max_results
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self.version = version
        self.default_stance = default_stance
        self.max_snippet_chars = max_snippet_chars
        self.name = f"MCP:{tool_name}"

    def search(self, task: DeepSearchTask) -> list[EvidenceRecord]:
        query = task.query.strip()
        if not query:
            raise ValueError("deep-search task query must be non-empty")
        arguments = {
            self.query_argument: query,
            self.limit_argument: self.max_results,
        }
        raw = _call_with_retries(
            self._client,
            tool_name=self.tool_name,
            arguments=arguments,
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            retry_backoff_seconds=self.retry_backoff_seconds,
        )
        version, evidence = parse_literature_mcp_result(
            raw,
            tool_name=self.tool_name,
            default_stance=self.default_stance,
            max_snippet_chars=self.max_snippet_chars,
            default_version=self.version,
        )
        self.version = version or self.version
        return evidence


def _pubmed_pmids(raw: dict[str, Any]) -> list[str]:
    pmids = raw.get("pmids")
    if not isinstance(pmids, list) or not all(isinstance(pmid, str) for pmid in pmids):
        raise LiteratureMCPError("PubMed search response requires a string pmids list")
    return list(dict.fromkeys(pmid.strip() for pmid in pmids if pmid.strip()))


def _pubmed_mesh_terms(article: dict[str, Any]) -> list[str]:
    terms = article.get("meshTerms")
    if not isinstance(terms, list):
        return []
    return [
        str(term["descriptorName"])
        for term in terms
        if isinstance(term, dict) and term.get("descriptorName")
    ]


def _pubmed_query(task: DeepSearchTask) -> str:
    """将结构化假说上下文收敛成 PubMed 可执行的 AND 查询。"""

    terms = [task.gene, task.disease_name or task.disease_id, task.organism]
    normalized = [_text(term).replace("\n", " ") for term in terms]
    normalized = [term for term in normalized if term]
    if normalized:
        return " AND ".join(f"({term})" for term in normalized)
    return task.query.replace("|", " AND ").strip()


def _pubmed_candidate_query(task: DeepSearchTask, candidate_gene: str) -> str:
    """构造跨物种近邻的补充查询，不沿用原始蛋白的物种过滤。"""

    terms = [candidate_gene, task.disease_name or task.disease_id]
    normalized = [_text(term).replace("\n", " ") for term in terms]
    normalized = [term for term in normalized if term]
    return " AND ".join(f"({term})" for term in normalized)


def parse_pubmed_fetch_result(
    raw: dict[str, Any],
    *,
    search_tool: str,
    fetch_tool: str,
    query: str,
    max_snippet_chars: int,
    query_scope: str = "primary",
    candidate_gene: str = "",
    primary_query: str = "",
) -> list[EvidenceRecord]:
    """把 PubMed fetch 的标题、摘要、MeSH 归一为可审计的中性证据。"""

    articles = raw.get("articles")
    if not isinstance(articles, list) or not all(isinstance(row, dict) for row in articles):
        raise LiteratureMCPError("PubMed fetch response requires an articles object list")

    evidence: list[EvidenceRecord] = []
    for index, article in enumerate(articles, start=1):
        pmid = _text(article.get("pmid"))
        title = _text(article.get("title"))
        if not pmid or not title:
            raise LiteratureMCPError(
                f"PubMed fetched article #{index} requires non-empty pmid and title"
            )
        doi = _text(article.get("doi"))
        pmc_id = _text(article.get("pmcId"))
        journal = article.get("journalInfo")
        journal_title = _text(journal.get("title")) if isinstance(journal, dict) else ""
        publication_types = article.get("publicationTypes")
        publication_types = (
            [str(value) for value in publication_types if isinstance(value, str)]
            if isinstance(publication_types, list)
            else []
        )
        evidence.append(
            EvidenceRecord(
                stance=EvidenceStance.NEUTRAL,
                title=title,
                reference=f"PMID:{pmid}",
                source="PubMed",
                snippet=_text(article.get("abstractText"))[:max_snippet_chars],
                provenance={
                    "mcp_search_tool": search_tool,
                    "mcp_fetch_tool": fetch_tool,
                    "query": query,
                    "query_scope": query_scope,
                    "result_index": index,
                    "pmid": pmid,
                    "doi": doi,
                    "pmc_id": pmc_id,
                    "journal": journal_title,
                    "mesh_terms": _pubmed_mesh_terms(article),
                    "publication_types": publication_types,
                    "pubmed_url": _text(article.get("pubmedUrl")),
                    **({"candidate_gene": candidate_gene} if candidate_gene else {}),
                    **({"primary_query": primary_query} if primary_query else {}),
                },
            )
        )
    return evidence


class PubMedLiteratureSearchSource:
    """调用本项目自托管 PubMed MCP 的两阶段文献召回源。"""

    name = "PubMed-MCP"

    def __init__(
        self,
        client: ToolCaller,
        *,
        search_tool: str = "pubmed_search_articles",
        fetch_tool: str = "pubmed_fetch_articles",
        max_results: int = 5,
        timeout_seconds: float = 20.0,
        max_attempts: int = 2,
        retry_backoff_seconds: float = 1.0,
        version: str = "pubmed-mcp-v2.9.8",
        max_snippet_chars: int = 1000,
        candidate_fallback_max_queries: int = 3,
    ) -> None:
        if not search_tool or not fetch_tool:
            raise ValueError("search_tool and fetch_tool must be non-empty")
        if max_results < 1 or timeout_seconds <= 0 or max_attempts < 1:
            raise ValueError("max_results, timeout_seconds, and max_attempts must be positive")
        if (
            retry_backoff_seconds < 0
            or max_snippet_chars < 0
            or candidate_fallback_max_queries < 0
        ):
            raise ValueError(
                "retry_backoff_seconds, max_snippet_chars, and "
                "candidate_fallback_max_queries must be non-negative"
            )
        self._client = client
        self.search_tool = search_tool
        self.fetch_tool = fetch_tool
        self.max_results = max_results
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self.version = version
        self.max_snippet_chars = max_snippet_chars
        self.candidate_fallback_max_queries = candidate_fallback_max_queries

    def _call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return _call_with_retries(
            self._client,
            tool_name=tool_name,
            arguments=arguments,
            timeout_seconds=self.timeout_seconds,
            max_attempts=self.max_attempts,
            retry_backoff_seconds=self.retry_backoff_seconds,
        )

    def _search_pmids(self, query: str) -> list[str]:
        search_raw = self._call(
            self.search_tool,
            {
                "query": query,
                "maxResults": self.max_results,
                "summaryCount": self.max_results,
                "hasAbstract": True,
            },
        )
        return _pubmed_pmids(search_raw)

    def _fetch_evidence(
        self,
        *,
        query: str,
        pmids: list[str],
        query_scope: str,
        candidate_gene: str = "",
        primary_query: str = "",
    ) -> list[EvidenceRecord]:
        fetch_raw = self._call(
            self.fetch_tool,
            {
                "pmids": pmids,
                "includeMesh": True,
                "includeGrants": False,
            },
        )
        evidence = parse_pubmed_fetch_result(
            fetch_raw,
            search_tool=self.search_tool,
            fetch_tool=self.fetch_tool,
            query=query,
            max_snippet_chars=self.max_snippet_chars,
            query_scope=query_scope,
            candidate_gene=candidate_gene,
            primary_query=primary_query,
        )
        if not evidence:
            raise LiteratureMCPError(
                "PubMed fetch returned no articles for non-empty search results"
            )
        return evidence

    def search(self, task: DeepSearchTask) -> list[EvidenceRecord]:
        primary_query = _pubmed_query(task)
        if not primary_query:
            raise ValueError("deep-search task query must be non-empty")
        pmids = self._search_pmids(primary_query)
        if pmids:
            return self._fetch_evidence(
                query=primary_query,
                pmids=pmids,
                query_scope="primary",
            )

        seen: set[str] = set()
        for raw_gene in task.candidate_genes:
            candidate_gene = _text(raw_gene)
            key = candidate_gene.casefold()
            if (
                not candidate_gene
                or key == _text(task.gene).casefold()
                or key in seen
            ):
                continue
            if len(seen) >= self.candidate_fallback_max_queries:
                break
            seen.add(key)
            fallback_query = _pubmed_candidate_query(task, candidate_gene)
            if not fallback_query or fallback_query == primary_query:
                continue
            pmids = self._search_pmids(fallback_query)
            if not pmids:
                continue
            return self._fetch_evidence(
                query=fallback_query,
                pmids=pmids,
                query_scope="candidate_fallback",
                candidate_gene=candidate_gene,
                primary_query=primary_query,
            )
        return []


class InMemoryLiteratureSource:
    """确定性测试/开发源：按 disease_id 预置证据。不作为生产源。"""

    name = "in-memory"
    version = "test"

    def __init__(
        self, by_disease: dict[str, list[EvidenceRecord]] | None = None
    ) -> None:
        self._by_disease = by_disease or {}

    def search(self, task: DeepSearchTask) -> list[EvidenceRecord]:
        return list(self._by_disease.get(task.disease_id, []))


def get_literature_search_source() -> LiteratureSearchSource:
    """按应用配置构建真实 MCP 文献检索源。"""

    from config import get_settings
    from pkg.mcp.client_pool import get_mcp_client

    cfg = get_settings().deep_search
    client = get_mcp_client(cfg.literature_mcp_endpoint)
    if cfg.provider == "pubmed":
        return PubMedLiteratureSearchSource(
            client,
            search_tool=cfg.mcp_tool,
            fetch_tool=cfg.fetch_mcp_tool,
            max_results=cfg.max_results,
            timeout_seconds=cfg.timeout_seconds,
            max_attempts=cfg.max_attempts,
            retry_backoff_seconds=cfg.retry_backoff_seconds,
            version=cfg.source_version,
            max_snippet_chars=cfg.max_snippet_chars,
            candidate_fallback_max_queries=cfg.candidate_fallback_max_queries,
        )
    return MCPLiteratureSearchSource(
        client,
        tool_name=cfg.mcp_tool,
        query_argument=cfg.query_argument,
        limit_argument=cfg.limit_argument,
        max_results=cfg.max_results,
        timeout_seconds=cfg.timeout_seconds,
        max_attempts=cfg.max_attempts,
        retry_backoff_seconds=cfg.retry_backoff_seconds,
        version=cfg.source_version,
        default_stance=EvidenceStance(cfg.default_stance),
        max_snippet_chars=cfg.max_snippet_chars,
    )


__all__ = [
    "InMemoryLiteratureSource",
    "LiteratureMCPError",
    "MCPLiteratureSearchSource",
    "PubMedLiteratureSearchSource",
    "ToolCaller",
    "get_literature_search_source",
    "parse_literature_mcp_result",
    "parse_pubmed_fetch_result",
]
