"""Foldseek 输出解析、近邻筛选与结构检索数据源。

纯逻辑（parse / select）可单测；真实 `foldseek easy-search` 调用经可注入的 runner，
因此不依赖二进制即可测；真实 Foldseek + AlphaFold DB 索引为外部依赖、联调时接入。
对标 `pkg.annotation.uniprot_mcp`（外部源归一为标准结果）。
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable, Iterable
from pathlib import Path

from pkg.structure.types import StructuralNeighbor

# 我们自己控制 foldseek --format-output，因此按固定列序解析（文件无表头）。
_FOLDSEEK_COLUMNS: tuple[str, ...] = (
    "query",
    "target",
    "fident",
    "qcov",
    "tcov",
    "prob",
    "evalue",
    "bits",
    "taxid",
    "taxname",
)

# Runner：给定一批 query accession，返回 foldseek 的原始 TSV 文本（一次检索全部）。
StructureSearchRunner = Callable[[list[str]], str]

_AF_RE = re.compile(r"AF-([A-Za-z0-9]+)-F\d+")
_STRUCT_SUFFIXES = (".cif.gz", ".pdb.gz", ".mmcif", ".cif", ".pdb", ".gz")


def _extract_accession(name: str) -> str:
    """从 AlphaFold 结构名/文件名抽 UniProt accession：AF-P12345-F1-... → P12345。"""

    name = name.strip()
    match = _AF_RE.search(name)
    if match:
        return match.group(1)
    for suffix in _STRUCT_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name


def _to_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_foldseek_output(
    lines: Iterable[str],
    *,
    columns: tuple[str, ...] = _FOLDSEEK_COLUMNS,
    version: str = "foldseek-unknown",
) -> dict[str, list[StructuralNeighbor]]:
    """解析 foldseek TSV → 按 query accession 归并的原始近邻（未排序、未筛选）。"""

    idx = {name: i for i, name in enumerate(columns)}
    core = max(idx["query"], idx["target"], idx["prob"], idx["tcov"])
    out: dict[str, list[StructuralNeighbor]] = {}
    for raw in lines:
        line = raw.rstrip("\n")
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) <= core:
            continue
        query = _extract_accession(fields[idx["query"]])
        target = _extract_accession(fields[idx["target"]])
        if not query or not target:
            continue
        taxid = _to_int(fields[idx["taxid"]]) if len(fields) > idx.get("taxid", 1 << 30) else None
        taxname = (
            fields[idx["taxname"]].strip() if len(fields) > idx.get("taxname", 1 << 30) else ""
        )
        out.setdefault(query, []).append(
            StructuralNeighbor(
                query_accession=query,
                target_accession=target,
                score=_to_float(fields[idx["prob"]]),
                coverage=_to_float(fields[idx["tcov"]]),
                taxon_id=taxid,
                taxon_name=taxname,
                relation_id=f"{query}->{target}",
                provenance={
                    "db_version": version,
                    "evalue": fields[idx["evalue"]] if len(fields) > idx.get("evalue", 1 << 30) else "",
                },
            )
        )
    return out


def select_neighbors(
    neighbors: list[StructuralNeighbor],
    *,
    top_k: int | None = None,
    min_score: float = 0.0,
    min_coverage: float = 0.0,
    exclude_self: bool = True,
) -> list[StructuralNeighbor]:
    """去自身 + 过阈值 + 按 score 降序 + 取 top-k + 重排 rank。"""

    filtered = [
        n
        for n in neighbors
        if (not exclude_self or n.target_accession != n.query_accession)
        and n.score >= min_score
        and n.coverage >= min_coverage
    ]
    filtered.sort(key=lambda n: n.score, reverse=True)
    if top_k is not None:
        filtered = filtered[:top_k]
    return [dataclasses.replace(n, rank=i + 1) for i, n in enumerate(filtered)]


class FoldseekStructureSearchProvider:
    """用 Foldseek 在 AlphaFold DB 上做结构近邻检索。"""

    name = "Foldseek-AlphaFold"

    def __init__(
        self,
        runner: StructureSearchRunner,
        *,
        version: str = "foldseek-unknown",
        top_k: int = 20,
        min_score: float = 0.0,
        min_coverage: float = 0.0,
        exclude_self: bool = True,
        columns: tuple[str, ...] = _FOLDSEEK_COLUMNS,
    ) -> None:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        self._runner = runner
        self.version = version
        self._top_k = top_k
        self._min_score = min_score
        self._min_coverage = min_coverage
        self._exclude_self = exclude_self
        self._columns = columns

    def search(
        self, accessions: list[str], *, top_k: int | None = None
    ) -> dict[str, list[StructuralNeighbor]]:
        unique = sorted({str(a).strip() for a in accessions if str(a).strip()})
        if not unique:
            return {}
        tsv = self._runner(unique)
        parsed = parse_foldseek_output(
            tsv.splitlines(), columns=self._columns, version=self.version
        )
        k = top_k if top_k is not None else self._top_k
        return {
            query: select_neighbors(
                parsed.get(query, []),
                top_k=k,
                min_score=self._min_score,
                min_coverage=self._min_coverage,
                exclude_self=self._exclude_self,
            )
            for query in unique
        }


def _make_foldseek_runner(cfg) -> StructureSearchRunner:
    """真实 `foldseek easy-search` runner（集成路径，需二进制 + AF DB + 本地查询结构）。"""

    def run(accessions: list[str]) -> str:
        import shutil
        import subprocess
        import tempfile

        from config.paths import project_root

        root = project_root()
        binary = cfg.foldseek_binary
        if shutil.which(binary) is None and not Path(binary).exists():
            raise RuntimeError(
                f"foldseek binary not found: {binary!r}；安装 Foldseek 或设 PTAGENT_STRUCTURE__FOLDSEEK_BINARY"
            )
        qdir = Path(cfg.query_structure_dir)
        qdir = qdir if qdir.is_absolute() else root / qdir
        afdb = Path(cfg.alphafold_db)
        afdb = afdb if afdb.is_absolute() else root / afdb

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            staged = tmp_path / "query"
            staged.mkdir()
            found = 0
            for accession in accessions:
                for candidate in sorted(qdir.glob(f"*{accession}*")):
                    (staged / candidate.name).symlink_to(candidate.resolve())
                    found += 1
                    break
            if found == 0:
                raise RuntimeError(f"no query structures found under {qdir} for given accessions")
            out_tsv = tmp_path / "result.tsv"
            subprocess.run(
                [
                    binary,
                    "easy-search",
                    str(staged),
                    str(afdb),
                    str(out_tsv),
                    str(tmp_path / "fs_tmp"),
                    "--format-output",
                    ",".join(cfg.format_columns),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            return out_tsv.read_text(encoding="utf-8")

    return run


def get_structure_search_provider() -> FoldseekStructureSearchProvider:
    from config import get_settings

    cfg = get_settings().structure
    return FoldseekStructureSearchProvider(
        _make_foldseek_runner(cfg),
        version=cfg.version,
        top_k=cfg.top_k,
        min_score=cfg.min_score,
        min_coverage=cfg.min_coverage,
        exclude_self=cfg.exclude_self,
        columns=tuple(cfg.format_columns),
    )


__all__ = [
    "FoldseekStructureSearchProvider",
    "StructureSearchRunner",
    "get_structure_search_provider",
    "parse_foldseek_output",
    "select_neighbors",
]
