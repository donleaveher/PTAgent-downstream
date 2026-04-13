"""肽段字符串分词、方括号增量解析、统一格式归一化。"""

from __future__ import annotations

from typing import List


def _parse_bracket_number(inner: str) -> float:
    """解析方括号内数字，支持 ``15.99``、``.98``、``0.984``。"""
    inner = inner.strip()
    if not inner:
        raise ValueError("empty bracket")
    if inner.startswith("."):
        inner = "0" + inner
    return float(inner)


def normalize_bracket_key(aa: str, inner: str) -> str:
    """生成规范键：``N[.98]`` 类保留前导点写法；其余四舍五入到 4 位小数。"""
    raw = inner.strip()
    if raw.startswith(".") and len(raw) > 1 and raw[1].isdigit():
        # 保留 .98 这种简写
        return f"{aa}[{raw}]"
    val = _parse_bracket_number(raw)
    if abs(val) < 1.0 and val != 0.0 and (raw.startswith("0.") or raw.startswith(".")):
        if raw.startswith("."):
            return f"{aa}[{raw}]"
    # 统一精度
    s = f"{val:.4f}".rstrip("0").rstrip(".")
    return f"{aa}[{s}]"


def tokenize_sequence(s: str) -> List[str]:
    """
    将肽段字符串拆成 token 列表。

    支持：``PEPTIDE``、``AM[15.99]IDE``、``N[.98]...``。
    单字母为 ``constants.AMINO_ACID_LETTERS``（标准 20 + U/O/B/Z/X 等）；其它字符跳过。
    """
    from .constants import AMINO_ACID_LETTERS

    s = s.strip().upper()
    tokens: List[str] = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch not in AMINO_ACID_LETTERS:
            i += 1
            continue
        if i + 1 < n and s[i + 1] == "[":
            j = s.find("]", i + 2)
            if j == -1:
                raise ValueError(f"unclosed bracket at position {i}")
            tokens.append(s[i : j + 1])
            i = j + 1
        else:
            tokens.append(ch)
            i += 1
    return tokens


def legacy_normalize_string(s: str) -> str:
    """将 ``M(ox)``、``C(carbamidomethyl)`` 等替换为统一方括号形式（最长键优先）。"""
    from .constants import LEGACY_TOKEN_TO_UNIFIED

    out = s
    for old, new in sorted(LEGACY_TOKEN_TO_UNIFIED.items(), key=lambda x: -len(x[0])):
        out = out.replace(old, new)
    return out


def split_legacy_tokens(s: str) -> List[str]:
    """
    在 legacy_normalize 之后，仍可能含 ``M(ox)`` 粘连时，
    用宽松规则按「大写字母 + 可选括号块」切分（备用）。
    """
    s = legacy_normalize_string(s)
    return tokenize_sequence(s)
