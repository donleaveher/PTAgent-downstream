"""Structured agent output: parse JSON from assistant text, validate with ``meta.output_json_schema``."""

from __future__ import annotations

import json
import re
from typing import Any

from jsonschema import Draft202012Validator

__all__ = [
    "extract_json_from_assistant_text",
    "validate_against_json_schema",
    "structured_output_instruction_suffix",
]


def structured_output_instruction_suffix(schema: dict[str, Any]) -> str:
    sch = json.dumps(schema, ensure_ascii=False, indent=2)
    return (
        "\n\n[Structured output] Your **final reply must be only** valid JSON (no prose outside it). "
        "It MUST validate against this JSON Schema:\n"
        f"{sch}"
    )


def extract_json_from_assistant_text(text: str) -> Any:
    """Parse JSON from full assistant text: whole string, then ```json``` fence, then first object/array."""
    s = (text or "").strip()
    if not s:
        raise ValueError("Empty model output")

    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", s)
    if m:
        inner = m.group(1).strip()
        try:
            return json.loads(inner)
        except json.JSONDecodeError:
            pass

    start_obj = s.find("{")
    start_arr = s.find("[")
    if start_obj >= 0 and (start_arr < 0 or start_obj < start_arr):
        depth = 0
        for i in range(start_obj, len(s)):
            c = s[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(s[start_obj : i + 1])
    elif start_arr >= 0:
        depth = 0
        for i in range(start_arr, len(s)):
            c = s[i]
            if c == "[":
                depth += 1
            elif c == "]":
                depth -= 1
                if depth == 0:
                    return json.loads(s[start_arr : i + 1])

    raise ValueError("Could not parse JSON from model output")


def validate_against_json_schema(instance: Any, schema: dict[str, Any]) -> None:
    Draft202012Validator(schema).validate(instance)
