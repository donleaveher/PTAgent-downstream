"""结构化输出解析与 JSON Schema 校验。"""

from __future__ import annotations

import pytest

from pkg.agent.structured_output import (
    extract_json_from_assistant_text,
    validate_against_json_schema,
)


def test_extract_plain_json() -> None:
    assert extract_json_from_assistant_text('{"a":1}') == {"a": 1}


def test_extract_fenced() -> None:
    t = 'note\n```json\n{"x": "y"}\n```\n'
    assert extract_json_from_assistant_text(t) == {"x": "y"}


def test_validate_schema() -> None:
    validate_against_json_schema({"a": 1}, {"type": "object", "required": ["a"], "properties": {"a": {"type": "integer"}}})


def test_validate_schema_fail() -> None:
    from jsonschema.exceptions import ValidationError

    with pytest.raises(ValidationError):
        validate_against_json_schema({"a": "no"}, {"type": "object", "properties": {"a": {"type": "integer"}}})
