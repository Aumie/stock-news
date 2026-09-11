from __future__ import annotations

import re

# User's exact question this was built for: "what symbol have most news in
# a day?" — RAG's top-k semantic retrieval can't answer an aggregate/count
# question across the whole dataset (it only pulls the handful of chunks
# most relevant to the question text, not everything), and the LLM
# correctly said so rather than guessing (decision_log_claude.md). A
# question matching this pattern is routed to a real SQL aggregate instead
# of vector retrieval. Deliberately a plain regex, not a second LLM call —
# a binary "is this an aggregate question" classification doesn't need the
# latency/cost of another model call.
_AGGREGATE_PATTERN = re.compile(
    r"\b(most|least|fewest|highest|lowest)\b.*\b(news|article|articles)\b",
    re.IGNORECASE,
)


def is_busiest_symbol_question(question: str) -> bool:
    return bool(_AGGREGATE_PATTERN.search(question))
