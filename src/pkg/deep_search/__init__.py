"""Deep-search 领域包（L4）：证据验证驱动假说的认知态跃迁。"""

from pkg.deep_search.source import (
    InMemoryLiteratureSource,
    LiteratureMCPError,
    MCPLiteratureSearchSource,
    PubMedLiteratureSearchSource,
    get_literature_search_source,
    parse_literature_mcp_result,
    parse_pubmed_fetch_result,
)
from pkg.deep_search.types import (
    DeepSearchTask,
    EvidenceRecord,
    EvidenceStance,
    LiteratureSearchSource,
)
from pkg.deep_search.verdict import DeepSearchVerdict, VerdictOutcome, decide_verdict

__all__ = [
    "DeepSearchTask",
    "DeepSearchVerdict",
    "EvidenceRecord",
    "EvidenceStance",
    "InMemoryLiteratureSource",
    "LiteratureMCPError",
    "LiteratureSearchSource",
    "MCPLiteratureSearchSource",
    "PubMedLiteratureSearchSource",
    "VerdictOutcome",
    "decide_verdict",
    "get_literature_search_source",
    "parse_literature_mcp_result",
    "parse_pubmed_fetch_result",
]
