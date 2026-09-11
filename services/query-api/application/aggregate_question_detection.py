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


# User's exact follow-up: "give me all 66 articles" then "cant we have it
# query all that?" — RAG retrieval only ever returns its top-k most
# semantically similar chunks (5 here), so it correctly refused to invent
# the other 61 rather than pretend it had them (decision_log_claude.md). A
# question asking to list/enumerate everything is a different shape from
# both an ordinary content question and a count/aggregate question — routed
# to a real SQL fetch of every matching article instead of vector retrieval.
_LIST_ALL_PATTERN = re.compile(
    r"\b(all|every|list|complete list)\b.*\b(news|article|articles)\b",
    re.IGNORECASE,
)


def is_list_all_articles_question(question: str) -> bool:
    return bool(_LIST_ALL_PATTERN.search(question))
