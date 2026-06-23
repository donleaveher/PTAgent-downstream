"""轻量占位 encoder：k-mer 组成向量（纯 numpy，无 torch）。

用途：先把「写 embedding → gds.knn → SIMILAR_TO」整条链路跑通验证，
之后替换成 ``esm_encoder.py`` 即可，上层（pkg/graph、application/graph）一行不改。

原理：把序列编码成 ``20**k`` 维的 k-mer 频率向量并 L2 归一化。
序列相似 ⇒ 共享 k-mer 多 ⇒ 余弦相似度高。仅作占位/基线，效果不及蛋白语言模型。
"""
from __future__ import annotations

import numpy as np

from pkg.embedding.base import STANDARD_AA, SequenceEncoder, normalize_sequence

# 标准氨基酸 → 稳定索引（排序保证跨进程可复现）
_AA_INDEX: dict[str, int] = {aa: i for i, aa in enumerate(sorted(STANDARD_AA))}
_N_AA: int = len(_AA_INDEX)


class KmerEncoder(SequenceEncoder):
    """k-mer 组成向量编码器。

    Args:
        k: k-mer 长度（默认 2，即二肽组成，维度 ``20**2 = 400``）。
           k 越大越精细但维度指数增长（k=3 → 8000 维），占位场景建议 2。
    """

    def __init__(self, k: int = 2) -> None:
        if k < 1:
            raise ValueError("k 必须 >= 1")
        self._k = k
        self._dim = _N_AA ** k

    @property
    def dim(self) -> int:
        return self._dim

    def _vectorize(self, seq: str) -> np.ndarray:
        """单条裸序列 → L2 归一化的 k-mer 频率向量。"""
        vec = np.zeros(self._dim, dtype=np.float64)
        for i in range(len(seq) - self._k + 1):
            idx = 0
            ok = True
            for ch in seq[i : i + self._k]:
                j = _AA_INDEX.get(ch)
                if j is None:            # 含非标准氨基酸（X/U…）的 k-mer 跳过
                    ok = False
                    break
                idx = idx * _N_AA + j
            if ok:
                vec[idx] += 1.0
        norm = float(np.linalg.norm(vec))
        if norm > 0.0:
            vec /= norm                  # 归一化后余弦相似度 = 点积；序列过短则保持零向量
        return vec

    def encode(self, sequences: list[str]) -> list[list[float]]:
        return [self._vectorize(normalize_sequence(s)).tolist() for s in sequences]


__all__ = ["KmerEncoder"]
