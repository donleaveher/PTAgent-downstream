"""精排：对融合后的候选用更贵的打分重排。scorer 可插拔(比对/交叉编码器/LLM-judge)。

默认 scorer 用 difflib 序列相似(纯 stdlib、确定性)当占位；真精排器日后替换同签名即可。
"""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Callable

Scorer = Callable[[str, str], float]        # (query, candidate) -> 分


def seq_identity(a: str, b: str) -> float:
    """两串的序列相似比(0~1)，占位精排打分。"""
    return SequenceMatcher(None, a, b).ratio()


def rerank(
    query: str,
    candidates: list[str],
    scorer: Scorer = seq_identity,
    top_k: int | None = None,
) -> list[tuple[str, float]]:
    """对候选逐条打分后降序；分相同按 id 升序定序。"""
    scored = sorted(
        ((c, scorer(query, c)) for c in candidates),
        key=lambda kv: (-kv[1], kv[0]),
    )
    return scored[:top_k] if top_k is not None else scored
