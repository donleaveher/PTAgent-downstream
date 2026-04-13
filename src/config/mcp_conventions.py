"""
应用侧：跨 MCP 工具的请求 / 响应字段命名约定（供 Admin 与业务代码对齐）。

``pkg.mcp.conventions.load_conventions_document`` 默认加载本模块；其它部署可设置
``PTAGENT_MCP_CONVENTIONS_MODULE`` 指向自有模块。

原则（简要）：

- **snake_case**，语义完整；同类概念用同一后缀（如 ``_da`` 表示 Dalton）。
- **机器侧序列**统一用 **词表整数下标** ``token_ids_*``，不用字符串 token 列表。
- **展示用**整条规范序列仍可用 ``normalized_sequence`` / ``peptide_with_ptm`` 等字符串字段。
- 嵌套对象按物理量分组（如 ``mass_da``），避免扁平键名冲突。
"""

from __future__ import annotations

from typing import Any

# —— 输入（常见） —— #
PEPTIDE_LEGACY = "peptide"  # 原始 / legacy 肽段字符串
CHARGE = "charge"
TOKEN_IDS_WITH_PTM = "token_ids_with_ptm"

# —— 输出（常见） —— #
NORMALIZED_SEQUENCE = "normalized_sequence"
TOKEN_IDS_BARE = "token_ids_bare"
MASS_DA = "mass_da"
RESIDUE_SUM = "residue_sum"
NEUTRAL_PEPTIDE = "neutral_peptide"
MZ = "mz"
RESIDUE_SUM_DA = "residue_sum_da"
NEUTRAL_MASS_DA = "neutral_mass_da"
PEPTIDE_WITH_PTM = "peptide_with_ptm"
PEPTIDE_BARE = "peptide_bare"

CONVENTIONS_DOCUMENT: dict = {
    "version": 1,
    "title": "PTAgent MCP 字段约定",
    "source_module": "config.mcp_conventions",
    "rules": [
        "键名使用 snake_case；单位写在键名里（如 _da）或 ISO 常识字段（mz, charge）。",
        "残基级序列在工具间传递时优先使用 token_ids_with_ptm（integer[]，词表下标），不使用字符串 token 数组。",
        "整条肽段展示仍可使用 normalized_sequence、peptide_with_ptm 等字符串。",
        "质量相关成组放在 mass_da 对象下：residue_sum、neutral_peptide。",
    ],
    "fields": [
        {
            "key": PEPTIDE_LEGACY,
            "json_schema_type": "string",
            "direction": "request",
            "note": "未规范化的输入肽段（含 legacy PTM 写法）",
        },
        {
            "key": CHARGE,
            "json_schema_type": "integer",
            "direction": "both",
            "note": "前体电荷 z（≥1）",
        },
        {
            "key": TOKEN_IDS_WITH_PTM,
            "json_schema_type": "array[integer]",
            "direction": "both",
            "note": "词表中带修饰残基的 token 下标序列（与 BasicPeptideToolkit.amino_acids 对齐）",
        },
        {
            "key": TOKEN_IDS_BARE,
            "json_schema_type": "array[integer]",
            "direction": "response",
            "note": "去修饰后的残基 token 下标序列",
        },
        {
            "key": NORMALIZED_SEQUENCE,
            "json_schema_type": "string",
            "direction": "response",
            "note": "规范拼接后的肽段字符串（含 […] 修饰）",
        },
        {
            "key": MASS_DA,
            "json_schema_type": "object",
            "direction": "response",
            "note": "质量（Da）：含 residue_sum、neutral_peptide",
        },
        {
            "key": MZ,
            "json_schema_type": "number",
            "direction": "response",
            "note": "前体 m/z（[M+zH]z+）",
        },
    ],
}

# —— LangGraph 编排 state.data 常用键（与 MCP 约定字段并列，供 /flow 勾选） —— #
WORKFLOW_BUILTIN_FIELDS: list[dict[str, Any]] = [
    {
        "key": "task",
        "json_schema_type": "string",
        "direction": "request",
        "note": "自然语言任务，写入初始 state.data",
    },
    {
        "key": "working_note",
        "json_schema_type": "string",
        "direction": "both",
        "note": "节点间传递的中间文本（与 ToolLlmAgent 约定一致）",
    },
    {
        "key": "message",
        "json_schema_type": "string",
        "direction": "request",
        "note": "与 task 类似的备用输入键",
    },
    {
        "key": "context",
        "json_schema_type": "string",
        "direction": "request",
        "note": "附加上下文",
    },
]


def workflow_data_key_catalog() -> dict[str, Any]:
    """
    供编排页「入口/出口字段」勾选：内置编排键 + 本文件 ``CONVENTIONS_DOCUMENT.fields`` 中的 MCP 约定键。
    """
    conv = CONVENTIONS_DOCUMENT.get("fields") if isinstance(CONVENTIONS_DOCUMENT, dict) else []
    conv_list = [x for x in conv if isinstance(x, dict) and x.get("key")]
    keys_builtin = [str(x["key"]) for x in WORKFLOW_BUILTIN_FIELDS]
    keys_conv = [str(x["key"]) for x in conv_list]
    return {
        "title": CONVENTIONS_DOCUMENT.get("title") if isinstance(CONVENTIONS_DOCUMENT, dict) else "",
        "builtinFields": list(WORKFLOW_BUILTIN_FIELDS),
        "conventionFields": conv_list,
        "allKeys": sorted(set(keys_builtin + keys_conv)),
    }


__all__ = [
    "CHARGE",
    "CONVENTIONS_DOCUMENT",
    "MASS_DA",
    "MZ",
    "NEUTRAL_MASS_DA",
    "NEUTRAL_PEPTIDE",
    "NORMALIZED_SEQUENCE",
    "PEPTIDE_BARE",
    "PEPTIDE_LEGACY",
    "PEPTIDE_WITH_PTM",
    "RESIDUE_SUM",
    "RESIDUE_SUM_DA",
    "TOKEN_IDS_BARE",
    "TOKEN_IDS_WITH_PTM",
    "WORKFLOW_BUILTIN_FIELDS",
    "workflow_data_key_catalog",
]
