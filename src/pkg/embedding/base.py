"""序列 embedding 抽象基类。

把「氨基酸序列 → 定长向量」与具体模型解耦：
- 上层（pkg/graph 写节点属性、gds.knn 算相似）只依赖本接口；
- 具体实现（本地 ESM、轻量 k-mer 占位、外部 MCP/服务）各自放独立模块；
- 输入是**裸序列**（stripped_sequence），不含修饰记法 —— 修饰 token 不被蛋白语言模型识别。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

# 20 种标准氨基酸（单字母）。非标准字符（X/U/B/Z/* 等）由各 encoder 自行决定如何处理。
STANDARD_AA: frozenset[str] = frozenset("ACDEFGHIKLMNPQRSTVWY")


def normalize_sequence(sequence: str) -> str:
    """编码前的统一清洗：去空白、转大写。

    只做与模型无关的规整；是否过滤/替换非标准氨基酸由具体 encoder 决定
    （不同模型对 X/U 等的处理不同）。
    """
    return "".join(sequence.split()).upper()


class SequenceEncoder(ABC):
    """氨基酸序列编码器抽象基类。

    企业级设计要求（对标 :class:`pkg.llm.base.LLMClient`）：
    - 不直接依赖具体模型（ESM、k-mer、外部服务等）；
    - 统一暴露最小接口（``encode``），便于在图谱 KNN 流程中替换实现；
    - 具体实现放独立模块（如 ``esm_encoder.py`` / ``kmer_encoder.py``）。

    接口约定：
    - ``encode`` 输入一批裸序列，**按顺序一一对应**返回等量向量；
    - 每个向量长度固定为 :pyattr:`dim`；
    - 实现内部可用 numpy/torch，但对外**只返回纯 ``list[float]``**
      （便于直接写进 Neo4j 节点属性、喂 ``gds.knn``）。
    """

    @property
    @abstractmethod
    def dim(self) -> int:
        """输出向量的维度（同一 encoder 实例对所有序列固定）。"""

    @abstractmethod
    def encode(self, sequences: list[str]) -> list[list[float]]:
        """批量编码。

        Args:
            sequences: N 条裸氨基酸序列。

        Returns:
            N 个长度为 :pyattr:`dim` 的向量，顺序与输入一致。

        实现注意：
        - 必须保证 ``len(返回) == len(sequences)``、且每个向量长度 == ``dim``；
        - 建议内部分批 + 对残基级输出做 mean-pool 成单条向量；
        - 空列表输入应返回空列表。
        """

    def encode_one(self, sequence: str) -> list[float]:
        """编码单条序列（默认走批量接口）。"""
        return self.encode([sequence])[0]


__all__ = ["SequenceEncoder", "normalize_sequence", "STANDARD_AA"]
