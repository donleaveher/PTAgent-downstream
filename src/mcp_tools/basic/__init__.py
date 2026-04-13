"""
``mcp_tools.basic``：聚合多个独立工具子项目。

- ``from mcp_tools.basic import BasicPeptideToolkit``
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .peptide import RESIDUE_MASS_BY_TOKEN, UNMODIFIED_RESIDUE_MASS, BasicPeptideToolkit

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
        from .peptide.provider import create_basic_peptide_tool_provider

        return create_basic_peptide_tool_provider()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
