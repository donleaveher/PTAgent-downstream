"""注释传递 / 标签传播：相似邻居的母蛋白属性 → 取共识 → 预测属性。纯函数。

置信度 = 相似度 × 共识度：
- 相似度 = 支持该属性的邻居的**平均相似度**（邻居有多像）；
- 共识度 = 支持该属性的邻居 / **全部邻居**（有多少邻居一致）。
单个弱邻居(共识低)或一堆不像的邻居(相似度低)都压不出高置信——这就是"取共识降噪"。

共享肽：邻居的属性按 accession 分组传入(``proteins``)，**压平只发生在这里、算共识那一刻**——
一个邻居"有"某属性 = 它**任一**蛋白带这属性；同时记下"经由哪些蛋白"当出处(support.via)。
"""
from __future__ import annotations

from collections.abc import Sequence

from pkg.hypothesis.base import Neighbor, Prediction

_ATTR_TYPES = ("go", "ec", "interpro")


def transfer_annotations(
    neighbors: Sequence[Neighbor],
    attr_types: Sequence[str] = _ATTR_TYPES,
    *,
    min_confidence: float = 0.0,
    top_n: int | None = None,
) -> list[Prediction]:
    """从邻居属性传递出预测列表，按置信度降序。

    Args:
        neighbors:      [{id, score, proteins: {accession: {go, ec, interpro}}}]。
        min_confidence: 低于此置信度的预测丢弃(降噪门槛)。
        top_n:          只留前 n 条。
    """
    n_total = len(neighbors)
    if n_total == 0:
        return []

    preds: list[Prediction] = []
    for t in attr_types:
        # value → [(邻居, 该邻居带此 value 的 accession 列表)]
        supporters: dict[str, list[tuple[Neighbor, list[str]]]] = {}
        for nb in neighbors:
            val_accs: dict[str, list[str]] = {}
            for acc, feats in (nb.get("proteins") or {}).items():
                for v in (feats.get(t) or []):
                    accs = val_accs.setdefault(v, [])
                    if acc not in accs:
                        accs.append(acc)
            for v, accs in val_accs.items():
                supporters.setdefault(v, []).append((nb, accs))

        for v, sup in supporters.items():
            sim = sum(float(nb.get("score") or 0.0) for nb, _ in sup) / len(sup)
            consensus = len(sup) / n_total          # 分母=全部邻居(没注释的邻居也算，会拉低共识)
            conf = sim * consensus
            if conf >= min_confidence:
                preds.append({
                    "attr_type": t,
                    "predicted": v,
                    "support": [{"neighbor": nb["id"], "via": accs} for nb, accs in sup],
                    "sim": sim,
                    "consensus": consensus,
                    "confidence": conf,
                })

    preds.sort(key=lambda p: (-p["confidence"], p["attr_type"], p["predicted"]))
    return preds[:top_n] if top_n is not None else preds
