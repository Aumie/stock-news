import pytest

from infrastructure.llm_client import AnthropicLLMClient


def test_raises_clear_error_when_api_key_missing():
    # regression guard: a missing key must fail loudly at construction time,
    # not surface as a generic crash mid-stream or get silently treated as a
    # spend-cap condition (docs/decision_log.md).
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        AnthropicLLMClient(api_key="")
