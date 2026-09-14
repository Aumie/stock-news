from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
import psycopg
import structlog

from prices.logging import configure_logging
from prices.prices_repo import PostgresPricesRepository
from prices.run_daily_batch import run_daily_batch
from prices.settings import Settings
from prices.symbol_resolution import resolve_range, resolve_symbols
from prices.yahoo_client import YahooClient

DBT_PROJECT_DIR = Path(__file__).parent / "dbt"

logger = structlog.get_logger()


def fetch_watched_symbols(conn: psycopg.Connection) -> list[str]:
    rows = conn.execute("SELECT DISTINCT symbol FROM watchlist").fetchall()
    return [row[0] for row in rows]


def dbt_env_from_database_url(database_url: str) -> dict[str, str]:
    # dbt's profiles.yml (services/daily-batch/dbt/profiles.yml) needs
    # discrete DBT_PG_HOST/PORT/USER/PASSWORD/DBNAME vars, but this service
    # only has a single DATABASE_URL secret (the same one every other
    # service uses) — locally, docker-compose.yml sets both separately, but
    # the cloud deploy has only DATABASE_URL, so derive the rest from it
    # here instead of introducing a second, redundant secret to keep in
    # sync with the first.
    # urlparse() returns username/password still percent-encoded (e.g. the
    # real secret's password contains a literal "@", encoded as %40) —
    # found live: dbt got the raw encoded string and failed Postgres auth
    # even though psycopg (which decodes internally) connected fine with
    # the exact same DATABASE_URL moments earlier in the same run.
    parsed = urlparse(database_url)
    env = dict(os.environ)
    env["DBT_PG_HOST"] = parsed.hostname or "localhost"
    env["DBT_PG_PORT"] = str(parsed.port or 5432)
    env["DBT_PG_USER"] = unquote(parsed.username) if parsed.username else "postgres"
    env["DBT_PG_PASSWORD"] = unquote(parsed.password) if parsed.password else ""
    env["DBT_PG_DBNAME"] = parsed.path.lstrip("/") or "stock-news"
    return env


def run_dbt(database_url: str) -> None:
    dbt_env = dbt_env_from_database_url(database_url)
    subprocess.run(
        ["dbt", "run", "--project-dir", str(DBT_PROJECT_DIR), "--profiles-dir", str(DBT_PROJECT_DIR)],
        check=True,
        env=dbt_env,
    )
    subprocess.run(
        ["dbt", "test", "--project-dir", str(DBT_PROJECT_DIR), "--profiles-dir", str(DBT_PROJECT_DIR)],
        check=True,
        env=dbt_env,
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pulls daily OHLCV and rebuilds daily_symbol_features via dbt."
    )
    parser.add_argument(
        "--symbol",
        default=None,
        help=(
            "Run for just this one symbol instead of every watched symbol — "
            "used for the on-add trigger (mirrors GCP Cloud Run Jobs API's "
            "per-execution argument; the scheduled daily sweep omits this "
            "and covers the whole watchlist, decision_log.md)."
        ),
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args(sys.argv[1:])
    settings = Settings()
    configure_logging(settings.log_env)

    # The shared database-url secret carries a "+psycopg" driver suffix for
    # SQLAlchemy-based services (processing/query-api) — psycopg.connect()
    # itself has no notion of that suffix (it's a SQLAlchemy-only dialect
    # convention) and fails to parse the URL with one present, so strip it
    # here rather than changing the shared secret and breaking those
    # services again. Same fix as poller's pgx driver (cmd/server/main.go).
    database_url = settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    conn = psycopg.connect(database_url)
    symbols = resolve_symbols(cli_symbol=args.symbol, watched_symbols=fetch_watched_symbols(conn))
    range_ = resolve_range(cli_symbol=args.symbol)
    logger.info("daily_batch.starting", symbol_count=len(symbols), range=range_)

    with httpx.Client(timeout=10.0) as http_client:
        yahoo_client = YahooClient(http_client=http_client)
        prices_repo = PostgresPricesRepository(conn)
        result = run_daily_batch(symbols=symbols, yahoo_client=yahoo_client, prices_repo=prices_repo, range_=range_)

    conn.commit()
    conn.close()
    logger.info(
        "daily_batch.prices_updated",
        succeeded=len(result.succeeded_symbols),
        failed=result.failed_symbols,
    )

    run_dbt(settings.database_url)
    logger.info("daily_batch.complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
