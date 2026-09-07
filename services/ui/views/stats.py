from __future__ import annotations

import os

import streamlit as st

from clients.stats_client import StatsAPIClient

QUERY_API_URL = os.environ.get("QUERY_API_URL", "http://localhost:8002")


def render() -> None:
    st.title("Stats & Cost Monitoring")

    client = StatsAPIClient(QUERY_API_URL)
    stats = client.get_stats(st.session_state["jwt"])

    overview = stats["overview"]
    col1, col2 = st.columns(2)
    col1.metric("Articles ingested today", overview["articles_ingested_today"])
    col2.metric("Tickers tracked", overview["tickers_tracked"])

    if not stats["by_symbol"]:
        st.write("No watched symbols yet — add some on the Watchlist page to see per-symbol stats.")
    else:
        for symbol, symbol_stats in stats["by_symbol"].items():
            st.subheader(symbol)

            volume_rows = symbol_stats["rolling_volume"]
            if volume_rows:
                st.write("7-day rolling article volume")
                st.line_chart(
                    {row["date"]: row["rolling_7day_avg"] for row in volume_rows},
                )

            lag = symbol_stats["ingestion_lag"]
            lag_col1, lag_col2, lag_col3 = st.columns(3)
            lag_col1.metric("Avg ingestion lag (s)", round(lag["avg_lag_seconds"], 1))
            lag_col2.metric("p50 lag (s)", round(lag["p50_lag_seconds"], 1))
            lag_col3.metric("p95 lag (s)", round(lag["p95_lag_seconds"], 1))

            price_rows = [row for row in symbol_stats["price_deltas"] if row["price_change_pct"] is not None]
            if price_rows:
                st.write("Day-over-day price change (%)")
                st.bar_chart({row["date"]: row["price_change_pct"] for row in price_rows})

    st.divider()
    st.subheader("Cloud cost monitoring")
    st.info(
        "Not available in local dev — this section queries BigQuery's "
        "INFORMATION_SCHEMA.JOBS for bytes scanned plus GCS/Pub-Sub usage APIs "
        "(§4.6), none of which exist until the milestone 7 cloud migration. "
        "Shown here, on the same page as stats rather than a separate one, "
        "per the spec's \"one surface, not two\" requirement."
    )
