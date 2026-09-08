from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

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


def run_dbt() -> None:
    subprocess.run(
        ["dbt", "run", "--project-dir", str(DBT_PROJECT_DIR), "--profiles-dir", str(DBT_PROJECT_DIR)],
        check=True,
    )
    subprocess.run(
        ["dbt", "test", "--project-dir", str(DBT_PROJECT_DIR), "--profiles-dir", str(DBT_PROJECT_DIR)],
        check=True,
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

    conn = psycopg.connect(settings.database_url)
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

    run_dbt()
    logger.info("daily_batch.complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
