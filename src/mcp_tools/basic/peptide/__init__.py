"""
basic 类目下的 **肽段** 子项目：``core`` 为纯逻辑；``provider`` 默认对接 ``pkg.mcp.provider``。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .core import RESIDUE_MASS_BY_TOKEN, UNMODIFIED_RESIDUE_MASS, BasicPeptideToolkit

if TYPE_CHECKING:
    from typing import Type

    BasicPeptideToolProvider: Type[Any]

__all__ = [
    "BasicPeptideToolProvider",
    "BasicPeptideToolkit",
    "RESIDUE_MASS_BY_TOKEN",
    "UNMODIFIED_RESIDUE_MASS",
]


def __getattr__(name: str) -> Any:
    if name == "BasicPeptideToolProvider":
        from .provider import create_basic_peptide_tool_provider

        return create_basic_peptide_tool_provider()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
