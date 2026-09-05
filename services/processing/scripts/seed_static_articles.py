"""Milestone 1 stand-in for the poller (docs/milestone.md §1).

Publishes a fixed, hardcoded set of articles for a fixed symbol list directly
to Processing's /pubsub/push endpoint, in the same envelope shape Pub/Sub
would use — so this gets replaced by a real queue in milestone 4 without
Processing's endpoint changing at all.
"""

from __future__ import annotations

import base64
import json
import sys
from datetime import datetime, timezone

import httpx

PROCESSING_URL = "http://localhost:8001/pubsub/push"

ARTICLES = [
    {
        "source": "finnhub",
        "headline": "Apple unveils new iPhone with on-device AI features",
        "published_at": datetime(2026, 9, 4, 14, 30, 0, tzinfo=timezone.utc).isoformat(),
        "content": (
            "Apple announced its latest iPhone lineup today, headlined by new "
            "on-device AI capabilities and an upgraded camera system. The company "
            "said the new features would roll out to developers next month."
        ),
        "symbol": "AAPL",
        "canonical_url": "https://example.com/news/apple-iphone-ai",
    },
    {
        "source": "marketaux",
        "headline": "Apple Unveils New iPhone With On-Device AI",
        "published_at": datetime(2026, 9, 4, 18, 0, 0, tzinfo=timezone.utc).isoformat(),
        "content": (
            "Apple's newest iPhone launch, announced earlier today, focuses heavily "
            "on artificial intelligence processed entirely on the device rather than "
            "in the cloud."
        ),
        "symbol": "AAPL",
        "canonical_url": None,
    },
    {
        "source": "finnhub",
        "headline": "Microsoft reports strong cloud growth in latest earnings",
        "published_at": datetime(2026, 9, 4, 16, 0, 0, tzinfo=timezone.utc).isoformat(),
        "content": (
            "Microsoft's Azure cloud division posted double-digit revenue growth "
            "this quarter, beating analyst expectations. The company credited "
            "enterprise AI adoption as a key driver."
        ),
        "symbol": "MSFT",
        "canonical_url": "https://example.com/news/msft-earnings",
    },
]


def _push_envelope(article: dict) -> dict:
    encoded = base64.b64encode(json.dumps(article).encode("utf-8")).decode("ascii")
    return {
        "message": {
            "data": encoded,
            "messageId": f"seed-{article['symbol']}-{article['published_at']}",
            "publishTime": datetime.now(timezone.utc).isoformat(),
        },
        "subscription": "projects/local/subscriptions/seed-script",
    }


def main() -> None:
    with httpx.Client() as client:
        for article in ARTICLES:
            response = client.post(PROCESSING_URL, json=_push_envelope(article))
            response.raise_for_status()
            print(f"seeded: {article['headline']!r} -> {response.json()}")


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPError as exc:
        print(f"seeding failed: {exc}", file=sys.stderr)
        sys.exit(1)
