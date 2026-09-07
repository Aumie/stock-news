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
    canonical_url TEXT UNIQUE,
    -- Computed once in Python (domain/dedup.py's normalize_headline) at insert
    -- time and matched exactly here — never re-derived with a second, separate
    -- SQL-side regex, which previously diverged from the Python normalization
    -- on non-ASCII headlines (decision_log_claude.md).
    normalized_headline TEXT NOT NULL
);

CREATE INDEX articles_fuzzy_match_idx ON articles (published_at, normalized_headline);

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

-- Local stand-in for BigQuery (docs/decision_log.md, "BigQuery for all
-- structured data" — no local BigQuery emulator exists, unlike Pub/Sub).
-- dbt targets this table via its postgres adapter locally, BigQuery at the
-- milestone 7 cloud migration.
CREATE TABLE prices (
    symbol TEXT NOT NULL,
    date DATE NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    volume BIGINT NOT NULL,
    PRIMARY KEY (symbol, date)
);
