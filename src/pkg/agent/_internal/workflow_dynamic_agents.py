"""工业编排专用节点：起点 / 纯 MCP 工具 / 终点（不经过 LLM）。"""

from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Sequence

from ..core import BaseAgent, RunContext


class StartWorkflowAgent(BaseAgent):
    """透传并校验入口字段（由 graph.inputKeys 声明）。"""

    def __init__(self, node_id: str, *, input_keys: Sequence[str] | None = None) -> None:
        super().__init__(name=node_id, description="workflow start")
        self._input_keys = [str(x).strip() for x in (input_keys or []) if str(x).strip()]

    def run(self, context: RunContext, state: Mapping[str, Any]) -> Dict[str, Any]:
        data = dict(state.get("data") or {})
        logs = list(state.get("logs") or [])
        missing = [k for k in self._input_keys if k not in data or data.get(k) in (None, "")]
        if missing:
            logs.append(f"[start:{self.name}] 缺少入口字段: {missing}")
        return {"data": data, "logs": logs}


class McpToolWorkflowAgent(BaseAgent):
    """单次 MCP tools/call；参数由 state.data 中若干键拼装。"""

    def __init__(
        self,
        node_id: str,
        *,
        tool_name: str,
        arg_keys: Sequence[str],
        output_key: str,
        call_tool: Any,
        flatten_dict_output: bool = True,
    ) -> None:
        super().__init__(name=node_id, description=f"MCP tool {tool_name}")
        self._tool_name = str(tool_name).strip()
        self._arg_keys = [str(x).strip() for x in arg_keys if str(x).strip()]
        self._output_key = (output_key or "").strip() or f"{node_id}_output"
        self._call_tool = call_tool
        self._flatten_dict_output = bool(flatten_dict_output)

    def run(self, context: RunContext, state: Mapping[str, Any]) -> Dict[str, Any]:
        data = dict(state.get("data") or {})
        logs = list(state.get("logs") or [])
        args = {k: data[k] for k in self._arg_keys if k in data}
        try:
            result = self._call_tool(self._tool_name, args)
        except Exception as exc:  # noqa: BLE001
            logs.append(f"[tool:{self.name}] 调用失败: {exc}")
            raise
        if isinstance(result, dict):
            text = json.dumps(result, ensure_ascii=False)
        else:
            text = str(result)

        if self._flatten_dict_output and isinstance(result, dict):
            merged = dict(data)
            overwritten: list[str] = []
            for k, v in result.items():
                ks = str(k)
                if ks in merged:
                    overwritten.append(ks)
                merged[ks] = v
            merged["working_note"] = text
            merged["last_tool"] = self._tool_name
            if overwritten:
                logs.append(f"[tool:{self.name}] 与已有 state.data 键重叠（后写覆盖）: {overwritten}")
            logs.append(f"[tool:{self.name}] ok（dict 输出已平铺至根键: {list(result.keys())}）")
            return {"data": merged, "logs": logs}

        merged = {**data, self._output_key: result, "working_note": text, "last_tool": self._tool_name}
        logs.append(f"[tool:{self.name}] ok")
        return {"data": merged, "logs": logs}


class EndWorkflowAgent(BaseAgent):
    """结束节点：约定出口键已在 ``state.data`` 根级，此处仅记日志。"""

    def __init__(self, node_id: str, *, output_keys: Sequence[str] | None = None) -> None:
        super().__init__(name=node_id, description="workflow end")
        self._output_keys = [str(x).strip() for x in (output_keys or []) if str(x).strip()]

    def run(self, context: RunContext, state: Mapping[str, Any]) -> Dict[str, Any]:
        data = dict(state.get("data") or {})
        logs = list(state.get("logs") or [])
        present = [k for k in self._output_keys if k in data]
        logs.append(f"[end:{self.name}] 约定出口键（已在 state.data 根级）: {present}")
        return {"data": data, "logs": logs}
