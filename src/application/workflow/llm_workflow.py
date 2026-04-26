"""从 LLM 回复中解析、规范化 workflow JSON；供向导/聊天 UI（产品层）。"""

from __future__ import annotations

import json
import re
from typing import Any, Iterator, Optional

_FENCE_PATTERNS = [
    re.compile(r"```workflow\s*([\s\S]*?)```", re.IGNORECASE),
    re.compile(r"```json\s*([\s\S]*?)```", re.IGNORECASE),
]


def _repair_trailing_commas(s: str) -> str:
    """去掉 JSON 中尾随逗号（模型常见笔误）。"""
    return re.sub(r",(\s*[}\]])", r"\1", s)


def _parse_json_lenient(raw: str) -> Any:
    """尝试解析 JSON；失败则修复尾随逗号后再试；再失败则从首个 ``{`` 起 ``raw_decode``。"""
    raw = raw.strip()
    if not raw:
        raise json.JSONDecodeError("empty", raw, 0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(_repair_trailing_commas(raw))
    except json.JSONDecodeError:
        pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(raw):
        if ch != "{":
            continue
        try:
            return dec.raw_decode(raw, i)[0]
        except json.JSONDecodeError:
            continue
    raise json.JSONDecodeError("no json object", raw, 0)


def _iter_json_objects_in_text(text: str) -> Iterator[Any]:
    """从文本中扫描所有能解析的顶层 JSON 对象（用于无代码围栏时的兜底）。"""
    dec = json.JSONDecoder()
    n = len(text)
    i = 0
    while i < n:
        j = text.find("{", i)
        if j < 0:
            return
        try:
            obj, end = dec.raw_decode(text, j)
            yield obj
            i = end
        except json.JSONDecodeError:
            i = j + 1


def normalize_workflow(data: Any) -> Optional[dict[str, Any]]:
    """
    将任意解析结果规范为 ``{"steps":[{id,title,tool,description},...], "notes"?: str}``。

    - 丢弃非 dict 的 step；为缺省字段补默认值。
    - 若无有效步骤则返回 ``None``。
    """
    if not isinstance(data, dict):
        return None
    steps_raw = data.get("steps")
    if not isinstance(steps_raw, list):
        return None
    norm_steps: list[dict[str, Any]] = []
    for i, s in enumerate(steps_raw):
        if not isinstance(s, dict):
            continue
        sid = s.get("id")
        sid_s = str(sid).strip() if sid is not None and str(sid).strip() else str(i + 1)
        title = s.get("title") or s.get("name") or s.get("step")
        title_s = str(title).strip() if title is not None else ""
        if not title_s:
            title_s = f"步骤 {i + 1}"
        tool = s.get("tool")
        if tool is None or tool == "":
            tool_out: str | None = None
        else:
            tool_out = str(tool).strip() or None
        desc = s.get("description") or s.get("detail") or s.get("desc") or ""
        norm_steps.append(
            {
                "id": sid_s,
                "title": title_s,
                "tool": tool_out,
                "description": str(desc).strip() if desc is not None else "",
            }
        )
    if not norm_steps:
        return None
    out: dict[str, Any] = {"steps": norm_steps}
    notes = data.get("notes")
    if notes is not None and str(notes).strip():
        out["notes"] = str(notes).strip()
    return out


def parse_workflow_from_text(text: str) -> Optional[dict[str, Any]]:
    """
    从模型输出中提取 workflow。

    顺序：

    1. ```workflow / ```json 代码块内 JSON；
    2. 代码块解析失败时，对块内字符串做宽松 ``json.loads``；
    3. 全文扫描所有 ``{...}`` 对象，取第一个能通过 :func:`normalize_workflow` 的对象。
    """
    if not text or not str(text).strip():
        return None

    candidates: list[str] = []
    for pat in _FENCE_PATTERNS:
        for m in pat.finditer(text):
            candidates.append(m.group(1).strip())

    seen: set[str] = set()
    for raw in candidates:
        if not raw or raw in seen:
            continue
        seen.add(raw)
        try:
            data = _parse_json_lenient(raw)
        except json.JSONDecodeError:
            continue
        wf = normalize_workflow(data)
        if wf:
            return wf

    for obj in _iter_json_objects_in_text(text):
        wf = normalize_workflow(obj)
        if wf:
            return wf

    return None


def fallback_workflow_from_text(text: str, *, max_desc: int = 1200) -> dict[str, Any]:
    """
    When no structured ``steps`` JSON can be parsed, return a **single-step** workflow so the UI
    still shows a pipeline card (narrative text in ``description``).

    Marked with ``notes: \"fallback_unparsed\"`` for clients that want to badge or log.
    """
    body = strip_workflow_fences_for_display(text) or (text or "").strip()
    if len(body) > max_desc:
        body = body[: max_desc - 1] + "…"
    if not body:
        body = "(No text in model reply.)"
    raw: dict[str, Any] = {
        "steps": [
            {
                "id": "1",
                "title": "Model output (unparsed)",
                "tool": None,
                "description": body,
            }
        ],
        "notes": "fallback_unparsed",
    }
    norm = normalize_workflow(raw)
    return norm if norm else raw


def workflow_to_json_text(wf: dict[str, Any], *, indent: int = 2) -> str:
    """将规范化后的 workflow 序列化为 JSON 字符串（写入日志/二次编辑）。"""
    return json.dumps(wf, ensure_ascii=False, indent=indent)


def strip_workflow_fences_for_display(text: str) -> str:
    """去掉 ```workflow / ```json 块，避免聊天区重复大段 JSON。"""
    if not text:
        return ""
    out = text
    for pat in _FENCE_PATTERNS:
        out = pat.sub("", out)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def format_mcp_tool_catalog_for_prompt(tools: list[dict[str, Any]], *, max_tools: int = 80) -> str:
    """紧凑列表，供 system 使用（工具名保持注册名，多为英文）。"""
    lines: list[str] = []
    for t in tools[:max_tools]:
        name = str(t.get("name") or "").strip()
        if not name:
            continue
        desc = str(t.get("description") or "").replace("\n", " ").strip()
        if len(desc) > 220:
            desc = desc[:217] + "…"
        cat = str(t.get("tool_category") or "").strip()
        grp = str(t.get("tool_group") or "").strip()
        meta = f" [{cat}" + (f" / {grp}" if grp else "") + "]" if cat else ""
        lines.append(f"- `{name}`{meta}: {desc}")
    return "\n".join(lines) if lines else "(no tools registered on MCP broker)"


__all__ = [
    "fallback_workflow_from_text",
    "format_mcp_tool_catalog_for_prompt",
    "normalize_workflow",
    "parse_workflow_from_text",
    "strip_workflow_fences_for_display",
    "workflow_to_json_text",
]
