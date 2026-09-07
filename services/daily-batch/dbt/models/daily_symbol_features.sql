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
)

select
    symbol,
    date,
    article_count,
    avg_ingestion_lag_seconds,
    price_close,
    price_volume,
    -- day-over-day % change, gated on both days actually having a price
    -- (no fabricated deltas across a gap where `prices` had no row)
    case
        when lag(price_close) over (partition by symbol order by date) is not null
             and lag(price_close) over (partition by symbol order by date) != 0
        then (price_close - lag(price_close) over (partition by symbol order by date))
             / lag(price_close) over (partition by symbol order by date) * 100
        else null
    end as price_change_pct
from priced
