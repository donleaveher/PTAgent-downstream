#!/usr/bin/env python3
"""把 CTD genes-diseases 大文件预处理成"只含直接证据"的精简 CSV + manifest。

CTD 全量文件混入海量"化学物推断"的间接关联（几千万行）。本脚本流式过滤，
只保留 DirectEvidence 命中的直接证据行（结论级），输出与原文件**同列布局**的精简
CSV——可被 `pkg.disease.ctd` 直接读取。旁路写 ``<output>.manifest.json``：源文件
sha256、保留行数、版本、时间，满足审计与可复现。

过滤规则与读取端共用 ``pkg.disease.ctd.iter_direct_evidence_rows``，不会漂移。

用法：
    python scripts/prepare_ctd.py <input.csv|.csv.gz> <output.csv> [--version CTD-2025-09]
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pkg.disease.ctd import iter_direct_evidence_rows  # noqa: E402

_HEADER_COMMENT = (
    "# GeneSymbol,GeneID,DiseaseName,DiseaseID,DirectEvidence,"
    "InferenceChemicalName,InferenceScore,OmimIDs,PubMedIDs"
)


def _iter_text(path: Path) -> Iterator[str]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        yield from handle


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def filter_ctd_file(
    input_path: str | Path,
    output_path: str | Path,
    *,
    version: str = "CTD-unknown",
    direct_evidence_types: tuple[str, ...] | None = None,
) -> dict:
    """流式过滤为直接证据精简 CSV，写 manifest，返回 manifest dict。"""

    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    kwargs = {}
    if direct_evidence_types is not None:
        kwargs["direct_evidence_types"] = direct_evidence_types

    scanned = 0
    kept = 0

    def _counted(lines: Iterator[str]) -> Iterator[str]:
        nonlocal scanned
        for line in lines:
            if line.strip() and not line.lstrip().startswith("#"):
                scanned += 1
            yield line

    with output_path.open("w", encoding="utf-8", newline="") as out:
        out.write(f"# CTD direct-evidence subset · version={version}\n")
        out.write(_HEADER_COMMENT + "\n")
        writer = csv.writer(out, lineterminator="\n")
        for row, _ in iter_direct_evidence_rows(_counted(_iter_text(input_path)), **kwargs):
            writer.writerow(row)
            kept += 1

    manifest = {
        "source_file": input_path.name,
        "source_sha256": _sha256(input_path),
        "source_size_bytes": input_path.stat().st_size,
        "output_file": output_path.name,
        "scanned_rows": scanned,
        "kept_direct_rows": kept,
        "kept_ratio": round(kept / scanned, 6) if scanned else 0.0,
        "version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = output_path.with_name(output_path.name + ".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Filter CTD genes-diseases to a direct-evidence subset."
    )
    parser.add_argument("input", help="CTD genes-diseases CSV 或 .csv.gz")
    parser.add_argument("output", help="输出精简 CSV 路径")
    parser.add_argument(
        "--version", default="CTD-unknown", help="CTD 版本标签（写入 manifest 与 provenance）"
    )
    args = parser.parse_args(argv)

    manifest = filter_ctd_file(args.input, args.output, version=args.version)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(
        f"\n[ok] kept {manifest['kept_direct_rows']} / {manifest['scanned_rows']} rows "
        f"({manifest['kept_ratio']:.2%} direct) -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
