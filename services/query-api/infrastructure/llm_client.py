from __future__ import annotations

from typing import Iterator

import anthropic
import structlog

logger = structlog.get_logger()

SPEND_CAP_MESSAGE = "This demo has a spending cap and it's been reached today."
CONFIG_ERROR_MESSAGE = "The LLM isn't configured correctly right now — this is a setup issue, not something retrying will fix."


class AnthropicLLMClient:
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5") -> None:
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. This is a deploy-time configuration error, "
                "not a runtime spend-cap condition, so it fails fast at startup rather than "
                "surfacing as a generic error mid-request."
            )
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def stream(self, prompt: str) -> Iterator[str]:
        # Real bug found live: an unhandled anthropic.BadRequestError (a real
        # account/key misconfiguration — an org-level key with no workspace
        # scope) propagated out of this generator mid-stream, which FastAPI's
        # StreamingResponse surfaces by simply closing the connection —
        # the UI sees an opaque httpx.RemoteProtocolError with no indication
        # anything LLM-side went wrong (decision_log_claude.md). Every branch
        # below must yield text instead of raising, so the stream always ends
        # with a real message rather than a silently severed connection.
        try:
            with self._client.messages.stream(
                model=self._model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                yield from stream.text_stream
        except anthropic.PermissionDeniedError:
            yield SPEND_CAP_MESSAGE
        except anthropic.RateLimitError:
            yield SPEND_CAP_MESSAGE
        except anthropic.BadRequestError as exc:
            # Found live: this except clause originally swallowed the error
            # with no logging at all — when a *second*, different
            # BadRequestError showed up after rotating the API key, there was
            # no way to tell from the logs whether it was the same
            # workspace-scoping issue or something new without removing the
            # try/except entirely (decision_log_claude.md).
            logger.warning("llm_client.bad_request", error=str(exc))
            yield CONFIG_ERROR_MESSAGE
