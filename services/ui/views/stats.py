from __future__ import annotations

import os

import streamlit as st

from clients.stats_client import StatsAPIClient

QUERY_API_URL = os.environ.get("QUERY_API_URL", "http://localhost:8002")


def render() -> None:
    st.title("Stats")

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

            state_key = f"stats_window_days_{symbol}"
            if state_key not in st.session_state:
                st.session_state[state_key] = 7

            window_col, _ = st.columns([1, 3])
            with window_col:
                choice = st.radio(
                    "Window",
                    options=[7, 30],
                    format_func=lambda d: f"{d}d",
                    horizontal=True,
                    index=[7, 30].index(st.session_state[state_key]),
                    label_visibility="collapsed",
                    key=f"stats_window_radio_{symbol}",
                )
            st.session_state[state_key] = choice
            window_stats = symbol_stats["window_7d"] if choice == 7 else symbol_stats["window_30d"]

            st.metric(f"Total ingestion (past {choice}d)", window_stats["total_articles"])

            volume_rows = window_stats["rolling_volume"]
            st.write(f"Daily article volume ({choice}d window)")
            if volume_rows:
                st.line_chart(
                    {row["date"]: row["articles_today"] for row in volume_rows},
                )
            else:
                st.caption("No data yet — this fills in once the daily batch job has run at least once.")

            price_rows = [row for row in window_stats["price_deltas"] if row["price_change_pct"] is not None]
            st.write("Day-over-day price change (%)")
            if price_rows:
                st.bar_chart({row["date"]: row["price_change_pct"] for row in price_rows})
            else:
                st.caption("No data yet — this fills in once the daily batch job has run at least once.")
