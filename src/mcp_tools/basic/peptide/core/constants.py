"""
原子质量、残基单同位素质量表与「统一 PTM 字符串」键。

统一约定（与常见 ProForma 思路一致）：
- 未修饰：单字母，如 ``G``、``M``。
- 修饰：``<AA>[<数值>]``，方括号内为相对**未修饰该氨基酸**的增量质量（Da），
  或简写如 ``N[.98]`` 表示 ``+0.98``（去酰胺化等）。
- 表 ``RESIDUE_MASS_BY_TOKEN`` 的值为该 **token 的绝对单同位素残基质量**（不含 H2O，与肽链内连接一致）。
"""

from __future__ import annotations

# —— 原子（单同位素，Da）——
H = 1.007825035
C = 12.0
N = 14.003074
O = 15.99491463
P = 30.973762
S = 31.972071

PROTON = 1.007276467
ELECTRON = 0.00054858

# 常用中性丢失 / 基团（与谱学脚本对齐，便于扩展）
CO = C + O
CHO = C + H + O
NH2 = N + H * 2
H2O = H * 2 + O
NH3 = N + H * 3
CO2 = C + O * 2

NEUTRAL_LOSS_MASS: dict[str, float] = {
    "CO": CO,
    "CO2": CO2,
    "CHO": CHO,
    "NH2": NH2,
    "H2O": H2O,
    "NH3": NH3,
    "H2S": H * 2 + S,
    "H": H,
    "H2": H * 2,
    "O": O,
    "OH": O + H,
    "CH3": C + H * 3,
}

# 未修饰氨基酸单同位素残基质量（肽链内，不含 H2O）
# 标准 20 + 常见扩展单字母（U/O/B/Z/X）；B/Z 为 Asx/Glx 模糊编码常用平均质量
UNMODIFIED_RESIDUE_MASS: dict[str, float] = {
    "G": 57.021464,
    "A": 71.037114,
    "S": 87.032028,
    "P": 97.052764,
    "V": 99.068414,
    "T": 101.047670,
    "C": 103.009184,
    "L": 113.084064,
    "I": 113.084064,
    "N": 114.042927,
    "D": 115.026943,
    "Q": 128.058578,
    "K": 128.094963,
    "E": 129.042593,
    "M": 131.040485,
    "H": 137.058912,
    "F": 147.068414,
    "R": 156.101111,
    "Y": 163.063329,
    "W": 186.079313,
    "U": 150.953636,  # 硒代半胱氨酸 Sec
    "O": 255.158295,  # 吡咯赖氨酸 Pyl（单同位素近似）
    "B": 114.53494,  # Asx（N/D 模糊）
    "Z": 128.55059,  # Glx（Q/E 模糊）
    "X": 110.0,  # 未知位点常用占位平均质量（可再调）
}

# 允许出现在无修饰分词中的单字母集合（供 parsing 使用）
AMINO_ACID_LETTERS: frozenset[str] = frozenset(UNMODIFIED_RESIDUE_MASS.keys())

# 变量修饰增量（相对未修饰侧链），用于生成/核对统一键名
PTM_DELTA_DA = {
    "OX": 15.99491,
    "PHOS": 79.966331,
    "ACET": 42.010565,
}

# 统一键 → 绝对残基质量（显式列举，便于与实验表对齐）
_UNIFIED_MOD_ABSOLUTE: dict[str, float] = {
    "C[57.02]": 160.030649,
    "M[15.99]": 147.035400,
    "N[.98]": 115.026943,
    "Q[.98]": 129.042594,
}

# 合并：所有可参与加和的 token → 绝对单同位素残基质量
RESIDUE_MASS_BY_TOKEN: dict[str, float] = {}
RESIDUE_MASS_BY_TOKEN.update(UNMODIFIED_RESIDUE_MASS)
RESIDUE_MASS_BY_TOKEN.update(_UNIFIED_MOD_ABSOLUTE)

# 旧式写法 → 统一键（用于 normalize）
LEGACY_TOKEN_TO_UNIFIED: dict[str, str] = {
    "C(carbamidomethyl)": "C[57.02]",
    "M(ox)": "M[15.99]",
    "N(deamide)": "N[.98]",
    "Q(deamide)": "Q[.98]",
}

__all__ = [
    "AMINO_ACID_LETTERS",
    "CO",
    "CO2",
    "CHO",
    "H",
    "H2O",
    "NH3",
    "NEUTRAL_LOSS_MASS",
    "PROTON",
    "ELECTRON",
    "PTM_DELTA_DA",
    "RESIDUE_MASS_BY_TOKEN",
    "UNMODIFIED_RESIDUE_MASS",
    "LEGACY_TOKEN_TO_UNIFIED",
]
