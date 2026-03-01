from __future__ import annotations

import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo


def market_profile_for(symbol: str, info: dict[str, Any] | None) -> tuple[ZoneInfo, int, int, int, int]:
    """Return market timezone and local open/close times for a symbol."""
    upper = symbol.upper()
    country = str((info or {}).get("country") or "").upper()
    currency = str((info or {}).get("currency") or "").upper()
    exchange = str((info or {}).get("exchange") or "").upper()
    is_india = (
        upper.endswith(".NS")
        or upper.endswith(".BO")
        or country == "INDIA"
        or currency == "INR"
        or exchange in {"NSE", "NSI", "BSE"}
        or upper.startswith("^NSE")
        or upper == "^BSESN"
    )
    if is_india:
        return ZoneInfo("Asia/Kolkata"), 9, 15, 15, 30
    return ZoneInfo("America/New_York"), 9, 30, 16, 0


def is_market_open_now(symbol: str, info: dict[str, Any] | None) -> bool:
    """Return True when the symbol's market is currently open."""
    tz, oh, om, ch, cm = market_profile_for(symbol, info)
    now = dt.datetime.now(tz)
    if now.weekday() >= 5:
        return False
    open_dt = now.replace(hour=oh, minute=om, second=0, microsecond=0)
    close_dt = now.replace(hour=ch, minute=cm, second=0, microsecond=0)
    return open_dt <= now <= close_dt


def interval_minutes(interval: str) -> int | None:
    """Convert supported intraday interval token to minutes."""
    mapping = {"1m": 1, "2m": 2, "5m": 5, "15m": 15, "30m": 30, "60m": 60, "90m": 90, "1h": 60}
    return mapping.get(interval.lower())


def extend_intraday_to_close(
    points: list[dt.datetime],
    prices: list[float],
    interval: str,
    symbol: str,
    info: dict[str, Any] | None,
) -> tuple[list[dt.datetime], list[float]]:
    """Extend intraday series to market close with NaN placeholders."""
    mins = interval_minutes(interval)
    if mins is None or not points:
        return points, prices
    tz, _, _, ch, cm = market_profile_for(symbol, info)
    last_local = points[-1].astimezone(tz)
    close_local = last_local.replace(hour=ch, minute=cm, second=0, microsecond=0)
    if last_local >= close_local:
        return points, prices

    out_points = list(points)
    out_prices = list(prices)
    nxt = last_local + dt.timedelta(minutes=mins)
    while nxt <= close_local:
        out_points.append(nxt.astimezone(dt.timezone.utc))
        out_prices.append(float("nan"))
        nxt += dt.timedelta(minutes=mins)
    return out_points, out_prices
