"""
MCP ``call_tool`` 成功返回的 **dict** 往往随工具实现变化（``results`` / ``data`` / ``items`` …）。

此处只做**与业务无关**的结构归一：抽出「列表结果」并补上统一元字段，便于上层展示或再包装。
"""

from __future__ import annotations

from typing import Any


def normalize_mcp_tool_dict_to_results(
    raw: dict[str, Any],
    *,
    query: str,
    size: int,
    list_key_candidates: tuple[str, ...] = ("results", "data", "items", "hits"),
    nested_list_key: str = "result",
) -> dict[str, Any]:
    """
    将 MCP 工具返回的 JSON 对象规范为至少包含 ``results: list`` 的 dict。

    - 若已有 ``results`` 且为 list：在原 dict 上 ``setdefault`` ``query`` / ``size`` 后返回副本式新 dict。
    - 否则按 ``list_key_candidates`` 依次查找第一个 **list** 值，写入 ``results``。
    - 若 ``nested_list_key``（默认 ``result``）对应 list，则作为 ``results``。
    - 仍无法解析时：``results`` 为空列表，并附 ``_mcpUnparsed``、``_rawKeys`` 便于排查。

    不修改调用方传入的 ``raw`` 本体（对外返回新 dict）。
    """
    if isinstance(raw.get("results"), list):
        out = dict(raw)
        out.setdefault("query", query)
        out.setdefault("size", size)
        return out

    for key in list_key_candidates:
        v = raw.get(key)
        if isinstance(v, list):
            merged = {k: raw[k] for k in raw if k != key}
            merged["query"] = query
            merged["size"] = size
            merged["results"] = v
            return merged

    nested = raw.get(nested_list_key)
    if isinstance(nested, list):
        return {
            **{k: raw[k] for k in raw if k != nested_list_key},
            "query": query,
            "size": size,
            "results": nested,
        }

    return {
        "query": query,
        "size": size,
        "results": [],
        "_mcpUnparsed": True,
        "_rawKeys": list(raw.keys()),
    }


__all__ = ["normalize_mcp_tool_dict_to_results"]
