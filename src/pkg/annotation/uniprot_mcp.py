"""UniProt MCP 工具到标准蛋白注释事实的适配器。"""

from __future__ import annotations

from typing import Any, Protocol

from pkg.annotation.knowledge import ProteinAnnotationFact


class ToolCaller(Protocol):
    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


_AGGREGATE_FIELDS: dict[str, str] = {
    "domain": "domain",
    "domains": "domain",
    "interpro": "interpro",
    "interpro_ids": "interpro",
    "tissue": "tissue",
    "tissues": "tissue",
    "tissue_expression": "tissue",
    "tissueExpression": "tissue",
    "organism": "organism",
    "organism_name": "organism",
    "taxon_id": "taxon_id",
    "taxonId": "taxon_id",
    "go": "go",
    "go_terms": "go",
    "goTerms": "go",
    "ec": "ec",
    "ec_numbers": "ec",
    "ecNumbers": "ec",
}


def _first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return None


def _accession(record: dict[str, Any], fallback: str | None = None) -> str:
    value = _first(record, "accession", "primaryAccession", "uniprot_id", "id")
    return str(value or fallback or "").strip()


def _values(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    if isinstance(value, str) and ";" in value:
        return [part.strip() for part in value.split(";") if part.strip()]
    return [value]


def _records(raw: dict[str, Any]) -> list[tuple[str | None, dict[str, Any]]]:
    """兼容 results/data/items、单记录和 accession→record 映射。"""

    for key in ("results", "data", "items", "hits", "result"):
        value = raw.get(key)
        if isinstance(value, list):
            return [(None, item) for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            if _accession(value):
                return [(None, value)]
            return [
                (str(accession), item)
                for accession, item in value.items()
                if isinstance(item, dict)
            ]
    if _accession(raw):
        return [(None, raw)]
    return [
        (str(accession), item)
        for accession, item in raw.items()
        if isinstance(item, dict)
    ]


def _version(raw: dict[str, Any], fallback: str) -> str:
    metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    value = _first(raw, "db_version", "dbVersion", "version") or _first(
        metadata, "db_version", "dbVersion", "version"
    )
    return str(value or fallback)


def parse_uniprot_mcp_result(
    raw: dict[str, Any],
    *,
    tool_name: str,
    default_version: str,
) -> tuple[str, dict[str, list[ProteinAnnotationFact]]]:
    """把 MCP 的常见返回形态归一为 accession→facts。"""

    version = _version(raw, default_version)
    out: dict[str, list[ProteinAnnotationFact]] = {}
    for fallback_accession, record in _records(raw):
        accession = _accession(record, fallback_accession)
        if not accession:
            continue
        facts = out.setdefault(accession, [])
        normalized = record.get("annotations")
        if isinstance(normalized, list):
            for item in normalized:
                if not isinstance(item, dict):
                    continue
                attribute = str(_first(item, "attribute", "type", "category") or "").strip()
                if not attribute or "value" not in item:
                    continue
                facts.append(
                    ProteinAnnotationFact(
                        accession=accession,
                        attribute=attribute,
                        value=item["value"],
                        source_ref=str(_first(item, "source_ref", "sourceRef", "ref") or "") or None,
                        evidence_code=str(
                            _first(item, "evidence_code", "evidenceCode", "evidence") or ""
                        )
                        or None,
                        provenance={
                            "mcp_tool": tool_name,
                            "db_version": version,
                        },
                    )
                )

        for source_key, attribute in _AGGREGATE_FIELDS.items():
            if source_key not in record:
                continue
            for value in _values(record[source_key]):
                facts.append(
                    ProteinAnnotationFact(
                        accession=accession,
                        attribute=attribute,
                        value=value,
                        provenance={
                            "mcp_tool": tool_name,
                            "db_version": version,
                            "source_field": source_key,
                        },
                    )
                )
    return version, out


class UniProtMCPAnnotationSource:
    """调用师兄的 UniProt MCP 工具，并适配为标准事实。"""

    name = "UniProt-MCP"

    def __init__(
        self,
        client: ToolCaller,
        *,
        tool_name: str,
        accessions_argument: str = "accessions",
        batch_size: int = 100,
        version: str = "MCP-current",
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self._client = client
        self.tool_name = tool_name
        self.accessions_argument = accessions_argument
        self.batch_size = batch_size
        self.version = version

    def fetch(self, accessions: list[str]) -> dict[str, list[ProteinAnnotationFact]]:
        unique = sorted({str(accession).strip() for accession in accessions if str(accession).strip()})
        out: dict[str, list[ProteinAnnotationFact]] = {}
        versions: list[str] = []
        for start in range(0, len(unique), self.batch_size):
            batch = unique[start : start + self.batch_size]
            raw = self._client.call_tool(self.tool_name, {self.accessions_argument: batch})
            if not isinstance(raw, dict):
                raise TypeError(f"UniProt MCP tool {self.tool_name!r} returned non-object result")
            version, parsed = parse_uniprot_mcp_result(
                raw,
                tool_name=self.tool_name,
                default_version=self.version,
            )
            versions.append(version)
            for accession, facts in parsed.items():
                out.setdefault(accession, []).extend(facts)
        if versions and len(set(versions)) == 1:
            self.version = versions[0]
        return out


def get_protein_annotation_source() -> UniProtMCPAnnotationSource:
    from config import get_mcp_settings, get_settings
    from pkg.mcp.client_pool import get_mcp_client

    app = get_settings()
    cfg = app.annotation
    client = get_mcp_client(get_mcp_settings().endpoint)
    return UniProtMCPAnnotationSource(
        client,
        tool_name=cfg.uniprot_mcp_tool,
        accessions_argument=cfg.accessions_argument,
        batch_size=cfg.batch_size,
        version=cfg.source_version,
    )


def _coerce_gene(value: Any) -> str:
    """把 UniProt 各种 gene 字段形态收敛成单个 symbol。"""

    if value is None or value == "":
        return ""
    if isinstance(value, str):
        return value.split(";")[0].strip()
    if isinstance(value, dict):
        return _coerce_gene(_first(value, "value", "name", "geneName", "symbol"))
    if isinstance(value, (list, tuple)):
        return _coerce_gene(value[0]) if value else ""
    return str(value).strip()


def _extract_gene(record: dict[str, Any]) -> str:
    return _coerce_gene(
        _first(
            record,
            "gene",
            "geneName",
            "gene_name",
            "geneSymbol",
            "gene_symbol",
            "primaryGeneName",
            "gene_primary",
            "genes",
        )
    )


def parse_uniprot_gene_map(raw: dict[str, Any]) -> dict[str, str]:
    """从 MCP 返回里抽 accession → gene symbol（兼容多种返回形态）。"""

    out: dict[str, str] = {}
    for fallback_accession, record in _records(raw):
        accession = _accession(record, fallback_accession)
        if not accession:
            continue
        gene = _extract_gene(record)
        if gene:
            out[accession] = gene
    return out


class UniProtMCPGeneResolver:
    """用师兄的 UniProt MCP 工具把 accession 解析成 gene symbol（供 M3 借 CTD 用）。"""

    name = "UniProt-MCP-gene"

    def __init__(
        self,
        client: ToolCaller,
        *,
        tool_name: str,
        accessions_argument: str = "accessions",
        batch_size: int = 100,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self._client = client
        self.tool_name = tool_name
        self.accessions_argument = accessions_argument
        self.batch_size = batch_size

    def resolve(self, accessions: list[str]) -> dict[str, str]:
        unique = sorted({str(a).strip() for a in accessions if str(a).strip()})
        out: dict[str, str] = {}
        for start in range(0, len(unique), self.batch_size):
            batch = unique[start : start + self.batch_size]
            raw = self._client.call_tool(self.tool_name, {self.accessions_argument: batch})
            if not isinstance(raw, dict):
                raise TypeError(
                    f"UniProt MCP tool {self.tool_name!r} returned non-object result"
                )
            out.update(parse_uniprot_gene_map(raw))
        return out


__all__ = [
    "ToolCaller",
    "UniProtMCPAnnotationSource",
    "UniProtMCPGeneResolver",
    "get_protein_annotation_source",
    "parse_uniprot_gene_map",
    "parse_uniprot_mcp_result",
]
