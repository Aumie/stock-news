from unittest.mock import MagicMock, patch

import anthropic
import httpx2
import pytest

from infrastructure.llm_client import CONFIG_ERROR_MESSAGE, AnthropicLLMClient


def test_raises_clear_error_when_api_key_missing():
    # regression guard: a missing key must fail loudly at construction time,
    # not surface as a generic crash mid-stream or get silently treated as a
    # spend-cap condition (docs/decision_log_claude.md).
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        AnthropicLLMClient(api_key="")


def test_bad_request_error_yields_a_config_error_message_instead_of_raising():
    # Real bug found live: an org-level API key with no workspace scope
    # raised anthropic.BadRequestError mid-stream, which propagated
    # unhandled out of this generator — FastAPI's StreamingResponse then
    # just closed the connection, surfacing to the UI as an opaque
    # httpx.RemoteProtocolError with zero indication anything LLM-side had
    # gone wrong (decision_log_claude.md). Every error branch here must
    # yield text, never raise, so the stream always ends with a real
    # message instead of a severed connection.
    client = AnthropicLLMClient(api_key="test-key")
    response = httpx2.Response(400, request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    error = anthropic.BadRequestError("bad request", response=response, body=None)

    with patch.object(client._client.messages, "stream", side_effect=error):
        chunks = list(client.stream("hello"))

    assert chunks == [CONFIG_ERROR_MESSAGE]
