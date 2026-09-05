from __future__ import annotations

from typing import Iterator

import anthropic

SPEND_CAP_MESSAGE = "This demo has a spending cap and it's been reached today."


class AnthropicLLMClient:
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001") -> None:
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. This is a deploy-time configuration error, "
                "not a runtime spend-cap condition, so it fails fast at startup rather than "
                "surfacing as a generic error mid-request."
            )
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def stream(self, prompt: str) -> Iterator[str]:
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
