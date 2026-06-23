"""过表达分析（ORA，"统计学角度"）。

纯函数：超几何检验 + BH FDR。**背景 = 本次鉴定蛋白池**（Q1，非全基因组——
避免检测丰度偏倚导致类别普遍虚假显著）。study 落在背景外的部分会被裁掉。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from scipy import stats


@dataclass(frozen=True)
class EnrichmentResult:
    term: str
    term_name: str
    overlap: int  # k：study ∩ term ∩ background
    term_size: int  # K：term ∩ background
    study_size: int  # n：study ∩ background
    background_size: int  # N
    p_value: float
    q_value: float
    fold_enrichment: float
    overlap_genes: tuple[str, ...]


def over_representation(
    study: Iterable[str],
    background: Iterable[str],
    gene_sets: dict[str, set[str]],
    *,
    term_names: dict[str, str] | None = None,
    min_overlap: int = 1,
) -> list[EnrichmentResult]:
    """对每个基因集做超几何过表达检验，返回按 p 升序的结果（已 BH 校正）。"""

    bg = set(background)
    st = set(study) & bg  # study 必须落在背景内
    background_size = len(bg)
    study_size = len(st)
    names = term_names or {}
    if background_size == 0 or study_size == 0:
        return []

    staged: list[tuple] = []
    for term, genes in gene_sets.items():
        term_in_bg = set(genes) & bg
        term_size = len(term_in_bg)
        if term_size == 0:
            continue
        overlap_genes = st & term_in_bg
        overlap = len(overlap_genes)
        if overlap < min_overlap:
            continue
        p_value = float(stats.hypergeom.sf(overlap - 1, background_size, term_size, study_size))
        fold = (overlap / study_size) / (term_size / background_size)
        staged.append(
            (term, names.get(term, term), overlap, term_size, p_value, fold, tuple(sorted(overlap_genes)))
        )
    if not staged:
        return []

    qvals = stats.false_discovery_control([row[4] for row in staged], method="bh")
    results = [
        EnrichmentResult(
            term=row[0],
            term_name=row[1],
            overlap=row[2],
            term_size=row[3],
            study_size=study_size,
            background_size=background_size,
            p_value=row[4],
            q_value=float(q),
            fold_enrichment=row[5],
            overlap_genes=row[6],
        )
        for row, q in zip(staged, qvals)
    ]
    results.sort(key=lambda e: (e.p_value, -e.overlap))
    return results


__all__ = ["EnrichmentResult", "over_representation"]
