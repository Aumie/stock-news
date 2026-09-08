from __future__ import annotations


def resolve_symbols(cli_symbol: str | None, watched_symbols: list[str]) -> list[str]:
    if cli_symbol is not None:
        return [cli_symbol]
    return watched_symbols


def resolve_range(cli_symbol: str | None) -> str:
    return "1mo" if cli_symbol is not None else "5d"
