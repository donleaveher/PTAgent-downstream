"""肽段基础工具：PTM 剥离/归一化、token↔index、单同位素质量。"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Union

from .constants import (
    H2O,
    NEUTRAL_LOSS_MASS,
    PROTON,
    RESIDUE_MASS_BY_TOKEN,
    UNMODIFIED_RESIDUE_MASS,
)
from .parsing import legacy_normalize_string, normalize_bracket_key, tokenize_sequence


# 同一质量多写法 → 规范键（展示用）
TOKEN_SYNONYMS: Dict[str, str] = {
    "M[15.9900]": "M[15.99]",
    "M[15.9949]": "M[15.99]",
    "C[57.0215]": "C[57.02]",
    "C[57.021]": "C[57.02]",
    "N[0.9840]": "N[.98]",
    "N[0.984]": "N[.98]",
    "Q[0.9840]": "Q[.98]",
    "Q[0.984]": "Q[.98]",
}


class BasicPeptideToolkit:
    """
    单同位素残基质量加和（**不含肽链 H2O**）；完整分子量可选 ``precursor_neutral_mass``。

    所有质量表来自 ``RESIDUE_MASS_BY_TOKEN`` / ``UNMODIFIED_RESIDUE_MASS``。
    """

    def __init__(self) -> None:
        self._build_vocabulary()

    def _build_vocabulary(self) -> None:
        specials = ["<PAD>", "<EOS>", "[CLS]", "[ENC]", "[DEC]", "[MASK]"]
        keys = sorted(RESIDUE_MASS_BY_TOKEN.keys(), key=lambda x: (len(x), x))
        self.amino_acids: List[str] = specials + keys
        self.token_to_idx: Dict[str, int] = {t: i for i, t in enumerate(self.amino_acids)}
        self.idx_to_token: Dict[int, str] = {i: t for i, t in enumerate(self.amino_acids)}

    # —— PTM / 字符串 —— #

    def strip_ptm(self, peptide: str) -> str:
        """去掉所有修饰，仅保留已收录单字母残基（标准 20 + U/O/B/Z/X 等扩展）。"""
        seq = legacy_normalize_string(peptide.strip())
        tokens = tokenize_sequence(seq)
        return "".join(t[0] for t in tokens if t and t[0] in UNMODIFIED_RESIDUE_MASS)

    def normalize_ptm_format(self, peptide: str) -> str:
        """
        将 legacy 写法替换为统一 ``AA[...]``，并把同义键合并为规范键。
        """
        seq = legacy_normalize_string(peptide.strip())
        tokens = tokenize_sequence(seq)
        out: List[str] = []
        for t in tokens:
            key = self._resolve_table_key(t)
            out.append(key)
        return "".join(out)

    def tokenize(self, peptide: str) -> List[str]:
        """分词为 token 列表（大写、legacy 已展开）。"""
        seq = legacy_normalize_string(peptide.strip())
        return tokenize_sequence(seq)

    def normalize_peptide_analysis(self, peptide: str) -> Dict[str, Any]:
        """归一化序列 + 分词结果（合并原 normalize + tokenize 输出）。"""
        seq = legacy_normalize_string(peptide.strip())
        raw_tokens = tokenize_sequence(seq)
        resolved: List[str] = []
        for t in raw_tokens:
            resolved.append(self._resolve_table_key(t))
        return {
            "normalized": "".join(resolved),
            "tokens": resolved,
        }

    def normalize_peptide_pipeline(self, peptide: str, charge: int = 1) -> Dict[str, Any]:
        """
        流程化：legacy/不规范 PTM → 规范键、拆 token（带修饰 / 不带修饰）、残基和、中性质量、m/z。
        """
        seq = legacy_normalize_string(peptide.strip())
        raw_tokens = tokenize_sequence(seq)
        tokens_with_ptm = [self._resolve_table_key(t) for t in raw_tokens]
        normalized_sequence = "".join(tokens_with_ptm)
        bare_sequence = "".join(t[0] for t in tokens_with_ptm if t and t[0] in UNMODIFIED_RESIDUE_MASS)
        residue_sum = self.calculate_residue_mass_sum(normalized_sequence)
        neutral = residue_sum + H2O
        mz = (neutral + charge * PROTON) / charge
        token_ids_with_ptm = self.peptide_to_index(normalized_sequence, strict=True)
        token_ids_bare = self.peptide_to_index(bare_sequence, strict=True)
        return {
            "normalized_sequence": normalized_sequence,
            "token_ids_with_ptm": token_ids_with_ptm,
            "token_ids_bare": token_ids_bare,
            "mass_da": {
                "residue_sum": residue_sum,
                "neutral_peptide": neutral,
            },
            "mz": mz,
            "charge": charge,
        }

    def peptide_mass_and_mz(self, token_ids_with_ptm: Sequence[int], charge: int = 1) -> Dict[str, Any]:
        """
        由 ``normalize_peptide`` 输出的 **token_ids_with_ptm**（词表下标）计算残基和、
        中性肽质量与 m/z。
        """
        ids = list(token_ids_with_ptm)
        normalized_sequence = self.index_to_peptide(ids)
        residue_sum = self.calculate_residue_mass_sum_from_token_ids(ids)
        neutral = residue_sum + H2O
        mz = (neutral + charge * PROTON) / charge
        return {
            "normalized_sequence": normalized_sequence,
            "token_ids_with_ptm": ids,
            "residue_sum_da": residue_sum,
            "neutral_mass_da": neutral,
            "mz": mz,
            "charge": charge,
        }

    def token_ids_to_canonical_peptides(self, token_ids_with_ptm: Sequence[int]) -> Dict[str, Any]:
        """由下标序列得到规范肽段字符串；无 PTM 侧给出 ``token_ids_bare``（非字符串列表）。"""
        ids = list(token_ids_with_ptm)
        joined = self.index_to_peptide(ids)
        bare = self.strip_ptm(joined)
        token_ids_bare = self.peptide_to_index(bare, strict=True)
        return {
            "peptide_with_ptm": joined,
            "peptide_bare": bare,
            "token_ids_bare": token_ids_bare,
        }

    def compute_mass(
        self,
        peptide: str,
        *,
        kind: str = "residue",
        charge: int = 1,
    ) -> float:
        """
        统一质量入口。

        - ``residue``：含修饰的残基质量和（无 H2O）
        - ``bare``：去修饰后按未修饰表加和
        - ``neutral``：中性肽 M = 残基和 + H2O
        - ``mz``：前体 m/z，需 ``charge`` ≥ 1
        """
        k = kind.lower().strip()
        if k == "residue":
            return self.calculate_residue_mass_sum(peptide)
        if k == "bare":
            return self.calculate_bare_residue_mass_sum(peptide)
        if k == "neutral":
            return self.precursor_neutral_mass(peptide)
        if k == "mz":
            return self.precursor_mz(peptide, charge=charge)
        raise ValueError(f"unknown mass kind: {kind!r}, expected residue|bare|neutral|mz")

    # —— index ↔ 序列 —— #

    def peptide_to_index(
        self,
        peptide: str,
        *,
        strict: bool = True,
    ) -> List[int]:
        """肽段字符串 → 词表下标。"""
        tokens = self.tokenize(peptide)
        out: List[int] = []
        for t in tokens:
            try:
                key = self._resolve_table_key(t)
            except KeyError:
                if strict:
                    raise
                continue
            if key not in self.token_to_idx:
                if strict:
                    raise KeyError(f"unknown token after resolve: {t!r} → {key!r}")
                continue
            out.append(self.token_to_idx[key])
        return out

    def index_to_peptide(self, indices: Sequence[int]) -> str:
        """词表下标 → 拼接后的肽段字符串（无分隔符）。"""
        parts: List[str] = []
        for i in indices:
            if i not in self.idx_to_token:
                raise KeyError(f"invalid index: {i}")
            t = self.idx_to_token[i]
            if t.startswith("<") or t.startswith("["):
                continue
            parts.append(t)
        return "".join(parts)

    # —— 质量 —— #

    def calculate_residue_mass_sum_from_token_ids(self, token_ids: Sequence[int]) -> float:
        """词表下标列表的残基质量和（单同位素，不含 H2O）。"""
        total = 0.0
        for i in token_ids:
            if i not in self.idx_to_token:
                raise KeyError(f"invalid token id: {i}")
            t = self.idx_to_token[i]
            if t.startswith("<") or t.startswith("["):
                continue
            key = self._resolve_table_key(t)
            if key not in RESIDUE_MASS_BY_TOKEN:
                raise KeyError(f"no mass for token id {i} → {key!r}")
            total += RESIDUE_MASS_BY_TOKEN[key]
        return total

    def calculate_residue_mass_sum(self, peptide_or_tokens: Union[str, Sequence[str]]) -> float:
        """
        肽段或 token 列表的**残基质量之和**（单同位素，**不含 H2O**，与常见脚本 ``calculate_pep_mass`` 一致）。
        """
        if isinstance(peptide_or_tokens, str):
            tokens = self.tokenize(peptide_or_tokens)
        else:
            tokens = list(peptide_or_tokens)
        total = 0.0
        for t in tokens:
            key = self._resolve_table_key(t)
            if key not in RESIDUE_MASS_BY_TOKEN:
                raise KeyError(f"no mass for token {t!r} (resolved {key!r})")
            total += RESIDUE_MASS_BY_TOKEN[key]
        return total

    def calculate_bare_residue_mass_sum(self, peptide: str) -> float:
        """去掉 PTM 后，仅按**未修饰**残基质量加和。"""
        bare = self.strip_ptm(peptide)
        total = 0.0
        for aa in bare:
            if aa not in UNMODIFIED_RESIDUE_MASS:
                raise KeyError(f"unknown bare AA: {aa!r}")
            total += UNMODIFIED_RESIDUE_MASS[aa]
        return total

    def calculate_modification_delta_mass(self, peptide: str) -> float:
        """``含修饰残基和 − 无修饰残基和``（近似为修饰总增量）。"""
        return self.calculate_residue_mass_sum(peptide) - self.calculate_bare_residue_mass_sum(peptide)

    def precursor_neutral_mass(self, peptide: str) -> float:
        """中性肽（M）质量 = 残基和 + H2O（羧基端 OH + 氨基端 H）。"""
        return self.calculate_residue_mass_sum(peptide) + H2O

    def precursor_mz(self, peptide: str, charge: int = 1) -> float:
        """简单 [M+zH]z+ m/z（charge≥1）。"""
        if charge < 1:
            raise ValueError("charge must be >= 1")
        neutral = self.precursor_neutral_mass(peptide)
        return (neutral + charge * PROTON) / charge

    def neutral_loss_mass(self, loss_key: str) -> float:
        """查中性丢失质量（如 ``H2O``、``NH3``）。"""
        if loss_key not in NEUTRAL_LOSS_MASS:
            raise KeyError(f"unknown loss: {loss_key!r}")
        return NEUTRAL_LOSS_MASS[loss_key]

    def vocabulary_size(self) -> int:
        return len(self.amino_acids)

    def list_vocabulary(self) -> List[str]:
        return list(self.amino_acids)

    def _resolve_table_key(self, token: str) -> str:
        t = token.strip()
        if t in TOKEN_SYNONYMS:
            t = TOKEN_SYNONYMS[t]
        if t in RESIDUE_MASS_BY_TOKEN:
            return t
        if len(t) >= 3 and t[1] == "[" and t.endswith("]"):
            aa, inner = t[0], t[2:-1]
            nk = normalize_bracket_key(aa, inner)
            if nk in RESIDUE_MASS_BY_TOKEN:
                return nk
            if nk in TOKEN_SYNONYMS:
                return TOKEN_SYNONYMS[nk]
        raise KeyError(f"cannot resolve token {token!r}")

    def describe_token(self, token: str) -> Dict[str, Any]:
        """调试：返回解析结果、是否在表内、质量。"""
        key = self._resolve_table_key(token)
        mass = RESIDUE_MASS_BY_TOKEN.get(key)
        idx = self.token_to_idx.get(key)
        return {
            "input": token,
            "canonical_key": key,
            "monoisotopic_residue_mass": mass,
            "vocabulary_index": idx,
        }


__all__ = ["BasicPeptideToolkit", "TOKEN_SYNONYMS"]
