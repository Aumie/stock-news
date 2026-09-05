-- Schema per docs/er-diagram.md. Applied on first container start via
-- docker-compose's postgres image /docker-entrypoint-initdb.d mount.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    google_sub TEXT UNIQUE NOT NULL,
    email TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE watchlist (
    user_id UUID NOT NULL REFERENCES users(id),
    symbol TEXT NOT NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, symbol)
);

CREATE TABLE articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    headline TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- headline + source + published_at rounded to the minute, NEVER ingested_at
    -- (docs/decision_log.md, "Deduplication")
    content_hash TEXT UNIQUE,
    canonical_url TEXT UNIQUE
);

CREATE TABLE article_symbols (
    article_id UUID NOT NULL REFERENCES articles(id),
    symbol TEXT NOT NULL,
    PRIMARY KEY (article_id, symbol)
);

CREATE TABLE embeddings (
    article_id UUID NOT NULL REFERENCES articles(id),
    chunk_index INT NOT NULL,
    vector vector(384) NOT NULL, -- all-MiniLM-L6-v2 dimensionality
    chunk_text TEXT NOT NULL,
    PRIMARY KEY (article_id, chunk_index)
);

CREATE INDEX embeddings_vector_idx ON embeddings USING hnsw (vector vector_cosine_ops);
