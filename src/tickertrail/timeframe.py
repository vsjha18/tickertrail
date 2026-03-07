from __future__ import annotations

import re

_PERIODS = ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max")
_INTERVALS = ("1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo", "1y")
_INTRADAY_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}


def normalize_period_token(period_token: str) -> str | None:
    """Normalize user period token; accepts d/w/mo/y units and 'max'."""
    token = period_token.strip().lower()
    if token == "max":
        return token
    if token in _PERIODS:
        return token
    match = re.fullmatch(r"(\d+)(d|w|mo|y)", token)
    if not match:
        return None
    n = int(match.group(1))
    if n <= 0:
        return None
    return f"{n}{match.group(2)}"


def period_token_days(period_token: str) -> int | None:
    """Approximate a normalized period token into calendar days."""
    token = normalize_period_token(period_token)
    if token is None or token == "max":
        return None
    mapping = {
        "1d": 1,
        "5d": 5,
        "1mo": 30,
        "3mo": 90,
        "6mo": 180,
        "1y": 365,
        "2y": 730,
        "5y": 1825,
        "10y": 3650,
    }
    if token in mapping:
        return mapping[token]
    match = re.fullmatch(r"(\d+)(d|w|mo|y)", token)
    if not match:
        return None
    n = int(match.group(1))
    unit = match.group(2)
    if unit == "d":
        return n
    if unit == "w":
        return n * 7
    if unit == "mo":
        return n * 30
    if unit == "y":
        return n * 365
    return None


def normalize_agg_token(token: str) -> str | None:
    """Normalize aggregation token to a yfinance interval string."""
    t = token.strip().lower()
    alias = {"m": "1m", "w": "1wk", "mo": "1mo", "d": "1d", "y": "1y"}
    if t in alias:
        return alias[t]
    if t in _INTERVALS:
        return t
    match = re.fullmatch(r"(\d+)m", t)
    if match and t in _INTERVALS:
        return t
    return None


def validate_period_interval(period_token: str, interval: str) -> str | None:
    """Validate period/interval compatibility and return an error message when invalid."""
    normalized_period = normalize_period_token(period_token)
    if normalized_period is None:
        return f"Unsupported period token '{period_token}'."
    if interval not in _INTERVALS:
        return f"Unsupported interval '{interval}'."
    if interval in _INTRADAY_INTERVALS:
        # Intraday data has strict retention windows on Yahoo Finance.
        if normalized_period == "max":
            return f"Interval '{interval}' is not supported with period 'max'."
        days = period_token_days(normalized_period)
        if days is None:
            return f"Cannot validate interval '{interval}' with period '{normalized_period}'."
        limit = 7 if interval == "1m" else 60
        if days > limit:
            return (
                f"Interval '{interval}' supports up to {limit}d lookback; "
                f"got '{normalized_period}'."
            )
    return None


def table_interval_for_period_token(period_token: str) -> str:
    """Pick default table aggregation interval from period token length."""
    token = normalize_period_token(period_token)
    if token == "max":
        return "1mo"
    days = period_token_days(period_token)
    if days is None:
        return "1d"
    # Table mode favors slower summary bins by default.
    if days <= 7:
        return "1d"
    if days <= 31:
        return "1wk"
    return "1mo"


def interval_for_chart_period(period_token: str) -> str:
    """Pick default chart interval from period token length."""
    token = normalize_period_token(period_token)
    if token == "max":
        return "1mo"
    days = period_token_days(period_token)
    if days is None:
        return "1d"
    if days >= 365 and days <= 730:
        return "1wk"
    if days > 730:
        return "1mo"
    return "1d"


def outperformance_pct(stock_value: float, bench_value: float) -> float:
    """Return outperformance in percent relative to benchmark value."""
    if bench_value == 0:
        return 0.0
    return ((stock_value / bench_value) - 1.0) * 100.0


def checkpoint_indices(length: int, points: int = 6) -> list[int]:
    """Return evenly spaced checkpoint indices for tabular summaries."""
    if length <= 0:
        return []
    if length <= points:
        return list(range(length))
    return sorted({round(i * (length - 1) / (points - 1)) for i in range(points)})
