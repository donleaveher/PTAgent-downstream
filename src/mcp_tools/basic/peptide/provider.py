"""
MCP 对接：与 ``pkg.mcp.provider`` 同处 ``src`` 下，直接 ``from pkg.mcp.provider import ...``。

可选环境变量 ``MCP_TOOL_PROVIDER_MODULE`` 指向其它模块（需导出 ``ToolProvider``、``tool``）。

:func:`run_blocking` 供 ``python -m mcp_tools.run_providers`` 使用。
"""

from __future__ import annotations

import importlib
import os
from typing import Any, Callable, Dict, List, Type

from .core import BasicPeptideToolkit


def _tool_provider_pair(module: str | None = None) -> tuple[Type[Any], Any]:
    """默认 ``pkg.mcp.provider``；否则按模块路径动态加载。"""
    name = module or os.environ.get("MCP_TOOL_PROVIDER_MODULE", "pkg.mcp.provider")
    if name == "pkg.mcp.provider":
        from pkg.mcp.provider import ToolProvider, tool

        return ToolProvider, tool
    m = importlib.import_module(name)
    return m.ToolProvider, m.tool


def create_basic_peptide_tool_provider(
    tool_provider_cls: Type[Any] | None = None,
    tool: Any = None,
) -> Type[Any]:
    """
    生成 ``BasicPeptideToolProvider``。未传入 ``tool_provider_cls`` / ``tool`` 时使用
    ``pkg.mcp.provider``（或 ``MCP_TOOL_PROVIDER_MODULE``）。
    """
    tp = tool_provider_cls
    td = tool
    if tp is None or td is None:
        tp2, td2 = _tool_provider_pair()
        tp = tp or tp2
        td = td or td2

    tk = BasicPeptideToolkit()

    class BasicPeptideToolProvider(tp):  # type: ignore[misc, valid-type]
        """肽段：3 个流程化 MCP 工具。"""

        provider_label = "basic-peptide"

        @td(
            description=(
                "流程：legacy PTM → 规范序列；输出 **token_ids_with_ptm / token_ids_bare**（词表整数下标，"
                "非字符串 token）；并给出 mass_da、m/z、charge。"
            ),
            category="basic",
            group="basic.peptide",
        )
        def normalize_peptide(self, peptide: str, charge: int = 1) -> Dict[str, Any]:
            return tk.normalize_peptide_pipeline(peptide, charge=charge)

        @td(
            description=(
                "输入 **token_ids_with_ptm**（与 normalize_peptide 输出同名字段，integer[]），"
                "计算残基和（Da）、中性肽质量（Da）、m/z 与 charge。"
            ),
            category="basic",
            group="basic.peptide",
        )
        def peptide_mass_and_mz(self, token_ids_with_ptm: List[int], charge: int = 1) -> Dict[str, Any]:
            return tk.peptide_mass_and_mz(token_ids_with_ptm, charge=charge)

        @td(
            description=(
                "由 **token_ids_with_ptm** 拼接规范肽段字符串（展示用），并给出无 PTM 序列及 **token_ids_bare**。"
            ),
            category="basic",
            group="basic.peptide",
        )
        def token_ids_to_peptide_strings(self, token_ids_with_ptm: List[int]) -> Dict[str, Any]:
            return tk.token_ids_to_canonical_peptides(token_ids_with_ptm)

    return BasicPeptideToolProvider


def run_blocking(endpoint: str, *, provider_module: str | None = None) -> None:
    tp, td = _tool_provider_pair(provider_module)
    cls = create_basic_peptide_tool_provider(tp, td)
    cls(endpoint).run()


__all__ = [
    "create_basic_peptide_tool_provider",
    "run_blocking",
]
