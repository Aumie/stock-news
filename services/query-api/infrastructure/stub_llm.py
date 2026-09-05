from __future__ import annotations

from typing import Iterator

STUB_NOTICE = (
    "[stub LLM response — set ANTHROPIC_API_KEY to get a real answer] "
    "Based on the retrieved articles above, here is a placeholder response."
)


class StubLLMClient:
    """Local-dev/demo stand-in so the stack runs with no Anthropic API key
    and no cost. Never used when ANTHROPIC_API_KEY is set — see presentation/api.py's
    wiring and docs/decision_log_claude.md ("cost-sensitive local dev").
    """

    def stream(self, prompt: str) -> Iterator[str]:
        yield STUB_NOTICE
