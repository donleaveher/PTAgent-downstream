"""pkg.mcp.tool_result_normalize — MCP 工具返回 dict 归一化。"""

from __future__ import annotations

from pkg.mcp.tool_result_normalize import normalize_mcp_tool_dict_to_results


def test_prefers_results_list() -> None:
    raw = {"results": [{"id": 1}], "foo": 1}
    out = normalize_mcp_tool_dict_to_results(raw, query="x", size=10)
    assert out["results"] == [{"id": 1}]
    assert out["query"] == "x"
    assert out["size"] == 10
    assert out["foo"] == 1


def test_maps_data_key() -> None:
    raw = {"data": [{"a": 2}], "meta": "m"}
    out = normalize_mcp_tool_dict_to_results(raw, query="q", size=5)
    assert out["results"] == [{"a": 2}]
    assert out["query"] == "q"
    assert "data" not in out
    assert out["meta"] == "m"


def test_unparsed_empty() -> None:
    raw = {"unexpected": 3}
    out = normalize_mcp_tool_dict_to_results(raw, query="q", size=1)
    assert out["results"] == []
    assert out.get("_mcpUnparsed") is True
    assert "unexpected" in out.get("_rawKeys", [])
