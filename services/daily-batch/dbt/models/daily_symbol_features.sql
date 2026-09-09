-- Feature-store-lite table (docs/stock-news-digest-requirements.md §4.6,
-- docs/er-diagram.md). Date grain is deliberately NOT gated on a `prices`
-- row existing: weekend/holiday news still needs a row (docs/decision_log.md,
-- "`daily_symbol_features`'s date grain is a union of `prices` dates and
-- article-activity dates").

with article_activity as (
    select
        article_symbols.symbol,
        articles.published_at::date as activity_date,
        extract(epoch from (articles.ingested_at - articles.published_at)) as ingestion_lag_seconds
    from articles
    inner join article_symbols on article_symbols.article_id = articles.id
),

date_grain as (
    select distinct symbol, date as activity_date from prices
    union
    select distinct symbol, activity_date from article_activity
),

article_stats as (
    select
        symbol,
        activity_date,
        count(*) as article_count,
        avg(ingestion_lag_seconds) as avg_ingestion_lag_seconds
    from article_activity
    group by symbol, activity_date
),

priced as (
    select
        date_grain.symbol,
        date_grain.activity_date as date,
        coalesce(article_stats.article_count, 0) as article_count,
        article_stats.avg_ingestion_lag_seconds,
        prices.close as price_close,
        prices.volume as price_volume
    from date_grain
    left join article_stats
        on article_stats.symbol = date_grain.symbol
        and article_stats.activity_date = date_grain.activity_date
    left join prices
        on prices.symbol = date_grain.symbol
        and prices.date = date_grain.activity_date
),

-- Postgres has no LAG(...) IGNORE NULLS, so the "last real price" is carried
-- forward manually: a running group id increments each time a real price
-- appears, then every null-price row (weekend/holiday) inherits that group's
-- one real price via a window MAX. Real bug found live: a plain
-- LAG(price_close) compares each row only to the literally previous row, so
-- Monday's change silently went null because it's "adjacent" to Sunday's
-- null price, not Friday's real one — even though a real day-over-day
-- comparison across the weekend gap is exactly what this column exists to
-- show (decision_log_claude.md).
carried as (
    select
        symbol,
        date,
        article_count,
        avg_ingestion_lag_seconds,
        price_close,
        price_volume,
        count(price_close) over (partition by symbol order by date) as price_group
    from priced
),

with_last_real_price as (
    select
        symbol,
        date,
        article_count,
        avg_ingestion_lag_seconds,
        price_close,
        price_volume,
        max(price_close) over (partition by symbol, price_group order by date) as last_real_price
    from carried
)

select
    symbol,
    date,
    article_count,
    avg_ingestion_lag_seconds,
    price_close,
    price_volume,
    -- day-over-day % change against the last day that actually had a price
    -- (skips weekend/holiday gaps instead of comparing to a null), still
    -- gated on that prior real price existing and being nonzero — no
    -- fabricated deltas when there's no earlier trading day at all
    case
        when price_close is not null
             and lag(last_real_price) over (partition by symbol order by date) is not null
             and lag(last_real_price) over (partition by symbol order by date) != 0
        then (price_close - lag(last_real_price) over (partition by symbol order by date))
             / lag(last_real_price) over (partition by symbol order by date) * 100
        else null
    end as price_change_pct
from with_last_real_price
