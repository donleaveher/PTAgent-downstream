"""normalize_openai_base_url / normalize_api_key_secret."""

from __future__ import annotations

from pkg.llm.openai_runtime import normalize_api_key_secret, normalize_openai_base_url


def test_normalize_strips_chat_completions_suffix() -> None:
    assert (
        normalize_openai_base_url("https://gpt-api.hkust-gz.edu.cn/v1/chat/completions")
        == "https://gpt-api.hkust-gz.edu.cn/v1"
    )


def test_normalize_plain_v1_unchanged() -> None:
    assert normalize_openai_base_url("https://api.openai.com/v1") == "https://api.openai.com/v1"


def test_normalize_empty() -> None:
    assert normalize_openai_base_url("") is None
    assert normalize_openai_base_url(None) is None


def test_normalize_bearer_key() -> None:
    assert normalize_api_key_secret("Bearer sk-test") == "sk-test"
    assert normalize_api_key_secret("bearer abc") == "abc"
