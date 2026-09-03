# ER diagram

Source of truth is `stock-news-digest-requirements.md` §7. This isn't one physical database — it's split across two engines (§4.6, §6), which changes what "foreign key" means in each half; noted below.

## Postgres (Supabase, pgvector) — v1

```mermaid
erDiagram
    users ||--o{ watchlist : "watches"
    articles ||--o{ article_symbols : "tagged with"
    articles ||--o{ embeddings : "chunked into"

    users {
        uuid id PK
        string google_sub UK
        string email
        timestamp created_at
    }

    watchlist {
        uuid user_id FK
        string symbol
        timestamp added_at
    }

    articles {
        uuid id PK
        string source
        string headline
        timestamp published_at
        timestamp ingested_at
        string content_hash UK "headline+source+published_at(min), NEVER ingested_at — see decision_log"
        string canonical_url UK "nullable; UNIQUE when present"
    }

    article_symbols {
        uuid article_id FK
        string symbol
    }

    embeddings {
        uuid article_id FK
        int chunk_index
        vector vector
        text chunk_text
    }
```

**Constraints that matter beyond the shape** (§4.3, §7 — these are why the dedup design actually holds):
- `articles.content_hash` UNIQUE, `ON CONFLICT DO NOTHING` — closes the within-source race
- `articles.canonical_url` UNIQUE when present, same conflict handling — closes the cross-source race whenever a source exposes a URL
- `article_symbols` composite UNIQUE `(article_id, symbol)` — makes the symbol-tagging insert idempotent
- `article_symbols` is deliberately many-to-many — one article can legitimately cover multiple tickers (sector news, or discovered via polling two different symbols)
- The one case with no hard constraint: cross-source matching via fuzzy-matched headline when no URL exists (§4.3's tier 3) — accepted, low-frequency edge case, not enforced at the DB level

## BigQuery — v1

```mermaid
erDiagram
    prices ||--o{ daily_symbol_features : "aggregated into"

    prices {
        string symbol
        date date
        float open
        float high
        float low
        float close
        int volume
    }

    daily_symbol_features {
        string symbol
        date date
        int article_count "via article_symbols join, not a direct articles.symbol count"
        float avg_ingestion_lag_seconds
        float price_close
        int price_volume
        float price_change_pct "day-over-day, dbt LAG()"
    }
```

- `prices` is **append-only, no rolling deletion** (§4.6, §5) — there is no FK from BigQuery back to Postgres; the join between `prices`/`daily_symbol_features` and `articles`/`article_symbols` happens inside the dbt model, not as an enforced database relationship, since they're different engines.
- `daily_symbol_features`'s date grain is the **union** of `prices` dates and article-activity dates, not gated on a `prices` row existing (§4.6) — a weekend with news but no trading still gets a row; price columns are null on those rows.
- Materialized as a dbt table (`materialized: table`), not a view — the aggregation is expensive enough and read frequently enough to earn it (§4.6).

## BigQuery — v2 additions (§12.5, not built yet)

```mermaid
erDiagram
    symbol_patterns {
        string symbol
        date date
        int window_days "one of 30/90/180/270/360 for the nightly-precomputed set; on-demand windows are computed fresh and not written here"
        string pattern_type "e.g. rising_wedge, falling_wedge, triangle, head_shoulder"
        date window_start
        date window_end
        timestamp detected_at
    }
```

Also v2: `articles.sentiment_score` (FinBERT, positive_prob − negative_prob) and `daily_symbol_features.avg_sentiment` (aggregated from it) — columns added to the v1 tables above, not new tables.
