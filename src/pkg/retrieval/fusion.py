"""RRF（Reciprocal Rank Fusion）：只看名次融合异构召回，无需校准各路打分。"""
from __future__ import annotations


def rrf(
    ranked_lists: list[list[str]],
    k: int = 60,
    top_n: int | None = None,
) -> list[tuple[str, float]]:
    """多路排名列表 → 融合排名。score(d) = Σ 1/(k + rank_i(d))，rank 从 1 起。

    各路打分量纲不同(余弦/bitscore/Jaccard/…)，RRF 只用名次，鲁棒、零调参。
    """
    scores: dict[str, float] = {}
    for lst in ranked_lists:
        for rank, cid in enumerate(lst):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked[:top_n] if top_n is not None else ranked
