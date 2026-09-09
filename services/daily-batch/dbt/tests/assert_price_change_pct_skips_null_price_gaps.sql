-- Real bug found live: a plain LAG(price_close) compared each row only to
-- the literally adjacent row, so the day right after a weekend/holiday gap
-- (no `prices` row) always got a null price_change_pct even though a real
-- comparison against the last actual trading day was available (TSLA:
-- Monday's change silently disappeared because it's adjacent to Sunday's
-- null, not Friday's real close — decision_log_claude.md).
--
-- This test fails if any row has a real price_close, a real price on some
-- earlier date for the same symbol exists, but price_change_pct is still
-- null — i.e. a comparison was possible but wasn't made.
select f.symbol, f.date
from {{ ref('daily_symbol_features') }} f
where f.price_close is not null
  and f.price_change_pct is null
  and exists (
      select 1
      from {{ ref('daily_symbol_features') }} earlier
      where earlier.symbol = f.symbol
        and earlier.date < f.date
        and earlier.price_close is not null
  )
