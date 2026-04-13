"""肽段子项目核心实现（常量、解析、Toolkit），不依赖 ``pkg.mcp``。"""

from .constants import (
    LEGACY_TOKEN_TO_UNIFIED,
    NEUTRAL_LOSS_MASS,
    PROTON,
    RESIDUE_MASS_BY_TOKEN,
    UNMODIFIED_RESIDUE_MASS,
)
from .parsing import legacy_normalize_string, normalize_bracket_key, tokenize_sequence
from .toolkit import TOKEN_SYNONYMS, BasicPeptideToolkit

__all__ = [
    "BasicPeptideToolkit",
    "LEGACY_TOKEN_TO_UNIFIED",
    "NEUTRAL_LOSS_MASS",
    "PROTON",
    "RESIDUE_MASS_BY_TOKEN",
    "TOKEN_SYNONYMS",
    "UNMODIFIED_RESIDUE_MASS",
    "legacy_normalize_string",
    "normalize_bracket_key",
    "tokenize_sequence",
]
