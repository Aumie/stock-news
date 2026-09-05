from __future__ import annotations

import base64
import json
from datetime import datetime

from pydantic import BaseModel

from domain.article import Article


class PubSubMessage(BaseModel):
    data: str
    messageId: str
    publishTime: str


class PubSubPushEnvelope(BaseModel):
    message: PubSubMessage
    subscription: str


class ArticlePayload(BaseModel):
    source: str
    headline: str
    published_at: datetime
    content: str
    symbol: str
    canonical_url: str | None = None


def parse_push_envelope(envelope: PubSubPushEnvelope) -> tuple[Article, str]:
    decoded = base64.b64decode(envelope.message.data)
    payload = ArticlePayload.model_validate(json.loads(decoded))
    article = Article(
        source=payload.source,
        headline=payload.headline,
        published_at=payload.published_at,
        content=payload.content,
        canonical_url=payload.canonical_url,
    )
    return article, payload.symbol
