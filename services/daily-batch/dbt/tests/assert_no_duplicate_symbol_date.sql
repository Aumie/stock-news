-- Composite-uniqueness test on (symbol, date) — dbt's singular-test
-- convention: a test "fails" if this query returns any rows.
select symbol, date, count(*)
from {{ ref('daily_symbol_features') }}
group by symbol, date
having count(*) > 1
