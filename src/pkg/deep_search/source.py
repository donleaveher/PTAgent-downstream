"""Deep-search 检索源实现：确定性内存源（测试/开发）+ 生产源工厂占位。

真实文献检索（DeepXiv / 文献 MCP 等）属外部依赖，活实例接好前由调用方注入 source；
:func:`get_literature_search_source` 默认显式报错，避免悄悄退化成 Mock 证据（§8.1）。
"""

from __future__ import annotations

from pkg.deep_search.types import DeepSearchTask, EvidenceRecord, LiteratureSearchSource


class InMemoryLiteratureSource:
    """确定性测试/开发源：按 disease_id 预置证据。不作为生产源。"""

    name = "in-memory"
    version = "test"

    def __init__(
        self, by_disease: dict[str, list[EvidenceRecord]] | None = None
    ) -> None:
        self._by_disease = by_disease or {}

    def search(self, task: DeepSearchTask) -> list[EvidenceRecord]:
        return list(self._by_disease.get(task.disease_id, []))


def get_literature_search_source() -> LiteratureSearchSource:
    """生产检索源工厂；真实工具接好前显式报错，要求调用方注入。"""

    raise NotImplementedError(
        "真实文献检索源（DeepXiv/文献 MCP 等）尚未接入；"
        "请向 deep-search 服务注入 source（§8.1 禁止使用 Mock 证据作为生产源）。"
    )


__all__ = ["InMemoryLiteratureSource", "get_literature_search_source"]
