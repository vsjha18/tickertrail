from __future__ import annotations

import calendar
import datetime as dt
import math
from bisect import bisect_right
from typing import Callable


def _subtract_months(anchor: dt.date, months: int) -> dt.date:
    """Return a date shifted back by N calendar months with day clamped."""
    year = anchor.year
    month = anchor.month - months
    while month <= 0:
        year -= 1
        month += 12
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


def _subtract_years(anchor: dt.date, years: int) -> dt.date:
    """Return a date shifted back by N calendar years with leap-day clamp."""
    try:
        return anchor.replace(year=anchor.year - years)
    except ValueError:
        # Handle Feb-29 -> Feb-28 fallback for non-leap target years.
        return anchor.replace(year=anchor.year - years, day=28)


def horizon_return_summary(
    symbol: str,
    fetch_closes: Callable[[str, str, str], tuple[list[object], list[float]]],
) -> dict[str, float | None]:
    """Compute calendar-anchored returns (7D/1MO/3MO/6MO/9MO/1Y) from one daily fetch."""
    points, closes = fetch_closes(symbol, "1y", "1d")
    return horizon_return_summary_from_points(points, closes)


def horizon_return_summary_from_points(
    points: list[object],
    closes: list[float | None],
) -> dict[str, float | None]:
    """Compute calendar-anchored returns from pre-fetched daily point/close arrays."""
    dated_closes: list[tuple[dt.date, float]] = []
    for point, close in zip(points, closes):
        if not isinstance(close, (int, float)) or not math.isfinite(float(close)):
            continue
        if isinstance(point, dt.datetime):
            dated_closes.append((point.date(), float(close)))
    if len(dated_closes) < 2:
        return {"7D": None, "1MO": None, "3MO": None, "6MO": None, "9MO": None, "1Y": None}

    dates = [row[0] for row in dated_closes]
    values = [row[1] for row in dated_closes]
    last_close = values[-1]
    last_date = dates[-1]

    def _pct_return_for_anchor(anchor_date: dt.date) -> float | None:
        """Return move versus last available close on/before the anchor date."""
        pos = bisect_right(dates, anchor_date)
        if pos == 0:
            return None
        base = values[pos - 1]
        if base == 0:
            return None
        return ((last_close / base) - 1.0) * 100.0

    # Calendar anchors with as-of lookup include all sessions between anchor and latest close.
    anchor_7d = last_date - dt.timedelta(days=7)
    anchor_1mo = _subtract_months(last_date, 1)
    anchor_3mo = _subtract_months(last_date, 3)
    anchor_6mo = _subtract_months(last_date, 6)
    anchor_9mo = _subtract_months(last_date, 9)
    anchor_1y = _subtract_years(last_date, 1)
    return {
        "7D": _pct_return_for_anchor(anchor_7d),
        "1MO": _pct_return_for_anchor(anchor_1mo),
        "3MO": _pct_return_for_anchor(anchor_3mo),
        "6MO": _pct_return_for_anchor(anchor_6mo),
        "9MO": _pct_return_for_anchor(anchor_9mo),
        "1Y": _pct_return_for_anchor(anchor_1y),
    }


def recent_direction_dots_from_points(
    closes: list[float | None],
    days: int,
    colorize: Callable[[str, str], str],
) -> str | None:
    """Return colored move dots from pre-fetched closes (older to latest)."""
    finite_closes = [float(close) for close in closes if isinstance(close, (int, float)) and math.isfinite(float(close))]
    if len(finite_closes) < days + 1:
        return None
    moves = finite_closes[-(days + 1) :]
    dots: list[str] = []
    for idx in range(1, len(moves)):
        diff = moves[idx] - moves[idx - 1]
        if diff > 0:
            dots.append(colorize("o", "green"))
        elif diff < 0:
            dots.append(colorize("o", "red"))
        else:
            dots.append(colorize("o", "yellow"))
    return "".join(dots)


def quote_signal_snapshot(
    points: list[object],
    closes: list[float | None],
    volumes: list[float | None],
) -> dict[str, float | str | None]:
    """Compute trend/momentum/volume/risk diagnostics from daily close-volume history."""
    dated_closes: list[tuple[dt.date, float]] = []
    for point, close in zip(points, closes):
        if not isinstance(close, (int, float)) or not math.isfinite(float(close)):
            continue
        if isinstance(point, dt.datetime):
            dated_closes.append((point.date(), float(close)))
    finite_volumes = [float(v) if isinstance(v, (int, float)) and math.isfinite(float(v)) else None for v in volumes]

    if len(dated_closes) < 2:
        return {
            "trend_score": None,
            "trend_total": 5.0,
            "rsi14": None,
            "vol_vs_20d": None,
            "max_drawdown_1y": None,
            "win_rate_1y": None,
            "best_day_pct": None,
            "best_day_date": None,
            "worst_day_pct": None,
            "worst_day_date": None,
            "skew_ratio": None,
        }

    dates = [row[0] for row in dated_closes]
    prices = [row[1] for row in dated_closes]
    last_close = prices[-1]

    def _sma(period: int) -> float | None:
        """Return simple moving average over the trailing `period` closes."""
        if len(prices) < period:
            return None
        window = prices[-period:]
        return sum(window) / float(period)

    sma20 = _sma(20)
    sma50 = _sma(50)
    sma200 = _sma(200)

    checks: list[bool] = []
    if sma20 is not None:
        checks.append(last_close > sma20)
    if sma50 is not None:
        checks.append(last_close > sma50)
    if sma200 is not None:
        checks.append(last_close > sma200)
    if sma20 is not None and sma50 is not None:
        checks.append(sma20 > sma50)
    if sma50 is not None and sma200 is not None:
        checks.append(sma50 > sma200)
    trend_score = float(sum(1 for item in checks if item))

    deltas = [prices[idx] - prices[idx - 1] for idx in range(1, len(prices))]
    gains = [value for value in deltas if value > 0]
    losses = [-value for value in deltas if value < 0]
    rsi14: float | None = None
    if len(deltas) >= 14:
        tail = deltas[-14:]
        avg_gain = sum(value for value in tail if value > 0) / 14.0
        avg_loss = sum(-value for value in tail if value < 0) / 14.0
        if avg_loss == 0:
            rsi14 = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi14 = 100.0 - (100.0 / (1.0 + rs))

    vol_vs_20d: float | None = None
    if len(finite_volumes) >= 21 and finite_volumes[-1] is not None:
        trail = [value for value in finite_volumes[-21:-1] if value is not None]
        if len(trail) == 20:
            baseline = sum(trail) / 20.0
            if baseline > 0:
                vol_vs_20d = float(finite_volumes[-1] / baseline)

    peak = prices[0]
    max_drawdown = 0.0
    for price in prices:
        if price > peak:
            peak = price
        drawdown = ((price / peak) - 1.0) * 100.0 if peak else 0.0
        if drawdown < max_drawdown:
            max_drawdown = drawdown

    day_returns: list[tuple[dt.date, float]] = []
    for idx in range(1, len(prices)):
        prev = prices[idx - 1]
        if prev == 0:
            continue
        pct = ((prices[idx] / prev) - 1.0) * 100.0
        day_returns.append((dates[idx], pct))

    win_rate: float | None = None
    if day_returns:
        wins = sum(1 for _date, pct in day_returns if pct > 0)
        win_rate = (wins / float(len(day_returns))) * 100.0

    best_day_pct: float | None = None
    best_day_date: str | None = None
    worst_day_pct: float | None = None
    worst_day_date: str | None = None
    if day_returns:
        best_date, best_val = max(day_returns, key=lambda row: row[1])
        worst_date, worst_val = min(day_returns, key=lambda row: row[1])
        best_day_pct = best_val
        best_day_date = best_date.strftime("%d-%m-%y")
        worst_day_pct = worst_val
        worst_day_date = worst_date.strftime("%d-%m-%y")

    skew_ratio: float | None = None
    if gains and losses:
        avg_up = sum(gains) / float(len(gains))
        avg_down = sum(losses) / float(len(losses))
        if avg_down > 0:
            skew_ratio = avg_up / avg_down

    return {
        "trend_score": trend_score,
        "trend_total": 5.0,
        "rsi14": rsi14,
        "vol_vs_20d": vol_vs_20d,
        "max_drawdown_1y": max_drawdown,
        "win_rate_1y": win_rate,
        "best_day_pct": best_day_pct,
        "best_day_date": best_day_date,
        "worst_day_pct": worst_day_pct,
        "worst_day_date": worst_day_date,
        "skew_ratio": skew_ratio,
    }


def recent_direction_dots(
    symbol: str,
    days: int,
    fetch_closes: Callable[[str, str, str], tuple[list[object], list[float]]],
    colorize: Callable[[str, str], str],
) -> str | None:
    """Return colored up/down dots left-to-right from older to latest daily moves."""
    # Use a buffered calendar window so we still get enough trading sessions.
    lookback_days = max((days + 1) * 3, 30)
    _points, closes = fetch_closes(symbol, f"{lookback_days}d", "1d")
    # Ignore non-finite values (for example NaN placeholders) before computing moves.
    return recent_direction_dots_from_points(closes=closes, days=days, colorize=colorize)
