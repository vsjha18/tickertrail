from __future__ import annotations

import datetime as dt
import math
import shutil
import sys
from typing import Any, Callable
from zoneinfo import ZoneInfo

import pandas as pd

from . import timeframe


def downsample_series(dates: list[str], prices: list[float], max_points: int) -> tuple[list[str], list[float]]:
    """Downsample paired date/price arrays to a display-friendly size."""
    if len(dates) <= max_points or max_points < 3:
        return dates, prices
    step = max(1, len(dates) // max_points)
    d_out = dates[::step]
    p_out = prices[::step]
    if d_out[-1] != dates[-1]:
        d_out.append(dates[-1])
        p_out.append(prices[-1])
    return d_out, p_out


def build_rebased_frame(
    stock_points: list[dt.datetime],
    stock_prices: list[float],
    bench_points: list[dt.datetime],
    bench_prices: list[float],
    tz: ZoneInfo,
    intraday: bool,
) -> pd.DataFrame | None:
    """Build aligned stock/benchmark frame with rebased metrics using pandas."""
    if not stock_points or not bench_points:
        return None
    s_idx = [int(p.timestamp()) for p in stock_points]
    b_idx = [int(p.timestamp()) for p in bench_points]
    s = pd.Series(stock_prices, index=s_idx, name="stock").groupby(level=0).last()
    b = pd.Series(bench_prices, index=b_idx, name="bench").groupby(level=0).last()
    frame = pd.concat([s, b], axis=1, join="inner").dropna()
    if frame.empty:
        return None
    if float(frame.iloc[0]["stock"]) == 0 or float(frame.iloc[0]["bench"]) == 0:
        return None

    stock0 = float(frame.iloc[0]["stock"])
    bench0 = float(frame.iloc[0]["bench"])
    frame["bench_on_stock_axis"] = frame["bench"] * (stock0 / bench0)
    dt_index = pd.to_datetime(frame.index, unit="s", utc=True).tz_convert(tz)
    frame["date"] = dt_index.strftime("%H:%M" if intraday else "%d-%m-%y")
    return frame


def build_multi_rebased_frame(
    series_by_symbol: list[tuple[str, list[dt.datetime], list[float]]],
    tz: ZoneInfo,
    intraday: bool,
) -> pd.DataFrame | None:
    """Align and rebase many symbol series to a shared base=100 frame."""
    if len(series_by_symbol) < 2:
        return None

    frame_parts: list[pd.Series] = []
    for symbol, points, prices in series_by_symbol:
        if not points or not prices:
            return None
        idx = [int(p.timestamp()) for p in points]
        series = pd.Series(prices, index=idx, name=symbol).groupby(level=0).last()
        frame_parts.append(series)

    frame = pd.concat(frame_parts, axis=1, join="inner").dropna()
    if frame.empty:
        return None

    for col in frame.columns:
        first_value = float(frame.iloc[0][col])
        if first_value == 0:
            return None
        frame[col] = frame[col] * (100.0 / first_value)

    dt_index = pd.to_datetime(frame.index, unit="s", utc=True).tz_convert(tz)
    frame["date"] = dt_index.strftime("%H:%M" if intraday else "%d-%m-%y")
    return frame


def print_rebased_table_output(
    symbol: str,
    benchmark_label: str,
    period_token: str,
    interval: str,
    dates: list[str],
    stock_values: list[float],
    bench_values: list[float],
    colorize: Callable[[str, str], str],
    color_by_sign: Callable[[float], str],
    checkpoint_indices_fn: Callable[[int, int], list[int]],
) -> None:
    """Print a normalized rebased stock-vs-benchmark table block."""
    if period_token.strip().lower() == "2y" and interval == "1mo" and len(dates) > 24:
        dates = dates[-24:]
        stock_values = stock_values[-24:]
        bench_values = bench_values[-24:]

    stock_100 = [100.0 * p / stock_values[0] for p in stock_values]
    bench_100 = [100.0 * p / bench_values[0] for p in bench_values]
    print(f"\nRebased Co-Plot (base=100): {symbol.upper()} vs {benchmark_label} [{period_token}, {interval}]")
    print(f"Date Range: {dates[0]} -> {dates[-1]}")
    intraday_intervals = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}
    sampling_note: str | None = None
    if interval == "1mo":
        row_indices = list(range(len(dates)))
    elif interval in intraday_intervals:
        max_rows = 24
        if len(dates) <= max_rows:
            row_indices = list(range(len(dates)))
        else:
            step = max(1, math.ceil(len(dates) / max_rows))
            row_indices = list(range(0, len(dates), step))
            if row_indices[-1] != len(dates) - 1:
                row_indices.append(len(dates) - 1)
            sampling_note = f"Sampled every {step} bars (base interval: {interval})."
    else:
        row_indices = checkpoint_indices_fn(len(dates), 6)
    print(f"{'Date':<10} {'Stock':>9} {'Bench':>9} {'Delta':>9} {'Alpha%':>9}")
    for idx in row_indices:
        stock_v = stock_100[idx]
        bench_v = bench_100[idx]
        delta = stock_v - bench_v
        alpha = timeframe.outperformance_pct(stock_v, bench_v)
        s_txt = colorize(f"{stock_v:>9.2f}", "cyan")
        b_txt = colorize(f"{bench_v:>9.2f}", "yellow")
        d_txt = colorize(f"{delta:>+9.2f}", color_by_sign(delta))
        a_txt = colorize(f"{alpha:>+8.2f}%", color_by_sign(alpha))
        print(f"{dates[idx]:<10} {s_txt} {b_txt} {d_txt} {a_txt}")
    if sampling_note is not None:
        print(sampling_note)
    final_rel = stock_100[-1] - bench_100[-1]
    final_rel_txt = colorize(f"{final_rel:+.2f}", color_by_sign(final_rel))
    final_alpha = timeframe.outperformance_pct(stock_100[-1], bench_100[-1])
    final_alpha_txt = colorize(f"{final_alpha:+.2f}%", color_by_sign(final_alpha))
    print(f"Final Relative (Stock - Bench): {final_rel_txt}")
    print(f"Final Alpha% (Stock vs Bench): {final_alpha_txt}")


def print_compare_table_output(
    resolved_symbols: list[str],
    period_token: str,
    interval: str,
    frame: pd.DataFrame,
    colorize: Callable[[str, str], str],
    color_by_sign: Callable[[float], str],
    checkpoint_indices_fn: Callable[[int, int], list[int]],
) -> None:
    """Print multi-instrument rebased table without delta/alpha columns."""
    dates = frame["date"].astype(str).tolist()
    if period_token.strip().lower() == "2y" and interval == "1mo" and len(dates) > 24:
        frame = frame.iloc[-24:].copy()
        dates = frame["date"].astype(str).tolist()

    print(f"\nCompare (base=100): {', '.join(resolved_symbols)} [{period_token}, {interval}]")
    print(f"Date Range: {dates[0]} -> {dates[-1]}")
    symbol_width = max(9, min(16, max(len(symbol) for symbol in resolved_symbols)))
    header = [f"{'Date':<10}", *[f"{symbol:>{symbol_width}}" for symbol in resolved_symbols]]
    print(" ".join(header))
    intraday_intervals = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}
    sampling_note: str | None = None
    if interval == "1mo":
        row_indices = list(range(len(dates)))
    elif interval in intraday_intervals:
        max_rows = 24
        if len(dates) <= max_rows:
            row_indices = list(range(len(dates)))
        else:
            step = max(1, math.ceil(len(dates) / max_rows))
            row_indices = list(range(0, len(dates), step))
            if row_indices[-1] != len(dates) - 1:
                row_indices.append(len(dates) - 1)
            sampling_note = f"Sampled every {step} bars (base interval: {interval})."
    else:
        row_indices = checkpoint_indices_fn(len(dates), 6)
    for idx in row_indices:
        cells = [f"{dates[idx]:<10}"]
        for symbol in resolved_symbols:
            value = float(frame.iloc[idx][symbol])
            cells.append(colorize(f"{value:>{symbol_width}.2f}", "cyan"))
        print(" ".join(cells))
    if sampling_note is not None:
        print(sampling_note)

    final_cells = [f"{'Final':<10}"]
    for symbol in resolved_symbols:
        value = float(frame.iloc[-1][symbol])
        move = value - 100.0
        final_cells.append(colorize(f"{value:>{symbol_width}.2f}", color_by_sign(move)))
    print(" ".join(final_cells))


def print_quote(
    input_symbol: str,
    resolved_symbol: str,
    include_after_hours: bool,
    preloaded_info: dict[str, Any] | None,
    get_quote_payload: Callable[[str], dict[str, Any]],
    recent_direction_dots_fn: Callable[[str, int], str | None],
    return_horizon_summary_fn: Callable[[str], dict[str, float | None]] | None,
    signal_snapshot_fn: Callable[[str], dict[str, float | str | None]] | None,
    colorize: Callable[[str, str], str],
    fmt_price: Callable[[Any], str],
    fmt_change: Callable[[Any, Any], str],
    fmt_compact_num: Callable[[Any], str],
    color_by_sign: Callable[[float], str],
    range_line: Callable[[float, float, float, int], str],
) -> int:
    """Render a compact quote snapshot with ranges, trend dots, and key ratios."""
    info = preloaded_info if preloaded_info is not None else get_quote_payload(resolved_symbol)
    if not info:
        print(f"Could not fetch quote for '{input_symbol}'.", file=sys.stderr)
        return 2

    name = str(info.get("shortName") or info.get("longName") or "n/a")
    currency = str(info.get("currency") or "n/a")
    price = info.get("regularMarketPrice")
    prev = info.get("regularMarketPreviousClose")
    change = None if price is None or prev is None else float(price) - float(prev)
    change_pct = None if change is None or not prev else (change / float(prev)) * 100
    open_px = info.get("regularMarketOpen")
    low_px = info.get("regularMarketDayLow")
    high_px = info.get("regularMarketDayHigh")
    wk52_low = info.get("fiftyTwoWeekLow")
    wk52_high = info.get("fiftyTwoWeekHigh")
    if wk52_low is None:
        wk52_low = info.get("yearLow")
    if wk52_high is None:
        wk52_high = info.get("yearHigh")
    volume = info.get("regularMarketVolume")
    market_cap = info.get("marketCap")
    trailing_pe = info.get("trailingPE")
    forward_pe = info.get("forwardPE")
    peg = info.get("trailingPegRatio")
    if peg is None:
        peg = info.get("pegRatio")
    roe = info.get("returnOnEquity")
    roce = info.get("returnOnCapitalEmployed")
    if roce is None:
        roce = info.get("roce")
    fcf = info.get("freeCashflow")

    now = dt.datetime.now().strftime("%d-%m-%y %H:%M:%S")
    price_txt = colorize(fmt_price(price), "cyan")
    chg_txt = colorize(fmt_change(change, change_pct), color_by_sign(float(change or 0.0)))
    print(f"\n{colorize(resolved_symbol, 'cyan')}  {name}  [{currency}]")
    print(
        f"Px {price_txt}  "
        f"Chg {chg_txt}  "
        f"O {fmt_price(open_px)}  "
        f"L/H {fmt_price(low_px)}/{fmt_price(high_px)}"
    )
    print(
        f"Vol {fmt_compact_num(volume)}  "
        f"MCap {fmt_compact_num(market_cap)}  "
        f"Updated {now}"
    )
    try:
        day_low_f = float(low_px) if low_px is not None else None
        day_high_f = float(high_px) if high_px is not None else None
        price_f = float(price) if price is not None else None
    except (TypeError, ValueError):
        day_low_f = day_high_f = price_f = None
    trend_dots = recent_direction_dots_fn(resolved_symbol, days=30)

    def _range_width_for_quote(label: str, low: float, high: float) -> int:
        """Compute quote range-bar width so the whole line usually fits in one terminal row."""
        cols = shutil.get_terminal_size(fallback=(120, 24)).columns
        suffix = f"{low:,.2f} .. {high:,.2f}"
        fixed = len(label) + 2 + len(suffix) + 2
        # Keep bars readable but clamp aggressively on narrow terminals.
        return max(18, min(40, cols - fixed))

    if day_low_f is not None and day_high_f is not None and price_f is not None and day_high_f > day_low_f:
        day_line = colorize(
            range_line(day_low_f, day_high_f, price_f, width=_range_width_for_quote("Day Range", day_low_f, day_high_f)),
            "cyan",
        )
        print(f"Day Range  {day_line}  {day_low_f:,.2f} .. {day_high_f:,.2f}")

    try:
        wk52_low_f = float(wk52_low) if wk52_low is not None else None
        wk52_high_f = float(wk52_high) if wk52_high is not None else None
    except (TypeError, ValueError):
        wk52_low_f = wk52_high_f = None
    if wk52_low_f is not None and wk52_high_f is not None and price_f is not None and wk52_high_f > wk52_low_f:
        wk52_line = colorize(
            range_line(
                wk52_low_f,
                wk52_high_f,
                price_f,
                width=_range_width_for_quote("52W Range", wk52_low_f, wk52_high_f),
            ),
            "yellow",
        )
        print(f"52W Range  {wk52_line}  {wk52_low_f:,.2f} .. {wk52_high_f:,.2f}")
    if trend_dots is not None:
        print(f"30D Moves  {trend_dots}")
    if return_horizon_summary_fn is not None:
        return_summary = return_horizon_summary_fn(resolved_symbol)

        def _fmt_return(value: float | None) -> str:
            """Format a horizon return with sign and fallback text."""
            if value is None:
                return "n/a"
            return f"{value:+.2f}%"

        # Keep return horizons directly under trend dots for quick timeframe scan.
        labels = ("7D", "1MO", "3MO", "6MO", "9MO", "1Y")
        parts: list[str] = []
        for label in labels:
            pct = return_summary.get(label)
            txt = _fmt_return(pct)
            if pct is None:
                parts.append(f"{label} {txt}")
            else:
                parts.append(f"{label} {colorize(txt, color_by_sign(pct))}")
        print(f"Returns    {'  '.join(parts)}")
    if signal_snapshot_fn is not None:
        signal = signal_snapshot_fn(resolved_symbol)

        def _fmt_pct(value: float | str | None) -> str:
            """Format percent values with sign and fallback text."""
            if not isinstance(value, (int, float)):
                return "n/a"
            return f"{float(value):+.2f}%"

        def _fmt_num(value: float | str | None, digits: int = 2) -> str:
            """Format numeric values with fallback for missing data."""
            if not isinstance(value, (int, float)):
                return "n/a"
            return f"{float(value):.{digits}f}"

        trend_score = signal.get("trend_score")
        trend_total = signal.get("trend_total")
        rsi14 = signal.get("rsi14")
        vol_vs_20d = signal.get("vol_vs_20d")
        max_drawdown = signal.get("max_drawdown_1y")
        win_rate = signal.get("win_rate_1y")
        best_day_pct = signal.get("best_day_pct")
        best_day_date = signal.get("best_day_date")
        worst_day_pct = signal.get("worst_day_pct")
        worst_day_date = signal.get("worst_day_date")
        skew_ratio = signal.get("skew_ratio")

        trend_txt = "n/a"
        if isinstance(trend_score, (int, float)) and isinstance(trend_total, (int, float)):
            trend_color = color_by_sign(float(trend_score) - (float(trend_total) / 2.0))
            trend_txt = colorize(f"{int(trend_score)}/{int(trend_total)}", trend_color)
        rsi_txt = _fmt_num(rsi14, digits=1)
        vol_txt = f"{_fmt_num(vol_vs_20d)}x" if isinstance(vol_vs_20d, (int, float)) else "n/a"
        maxdd_txt = _fmt_pct(max_drawdown)
        if isinstance(max_drawdown, (int, float)):
            maxdd_txt = colorize(maxdd_txt, color_by_sign(float(max_drawdown)))
        win_txt = _fmt_num(win_rate) + "%" if isinstance(win_rate, (int, float)) else "n/a"

        best_txt = _fmt_pct(best_day_pct)
        if isinstance(best_day_pct, (int, float)):
            best_txt = colorize(best_txt, color_by_sign(float(best_day_pct)))
        worst_txt = _fmt_pct(worst_day_pct)
        if isinstance(worst_day_pct, (int, float)):
            worst_txt = colorize(worst_txt, color_by_sign(float(worst_day_pct)))
        best_lbl = f"{best_txt} ({best_day_date})" if isinstance(best_day_date, str) else best_txt
        worst_lbl = f"{worst_txt} ({worst_day_date})" if isinstance(worst_day_date, str) else worst_txt
        skew_txt = _fmt_num(skew_ratio)

        print(f"Signal     TrendScore {trend_txt}  RSI14 {rsi_txt}  Vol/20D {vol_txt}")
        print(f"Risk       MaxDD(1Y) {maxdd_txt}  WinRate(1Y) {win_txt}")
        print(f"Extremes   Best {best_lbl}  Worst {worst_lbl}  Skew {skew_txt}")

    def _fmt_ratio(value: Any, pct: bool = False) -> str:
        """Format ratio values, optionally as percent."""
        try:
            v = float(value)
        except (TypeError, ValueError):
            return "n/a"
        if pct:
            return f"{v*100:.2f}%"
        return f"{v:.2f}"

    ratio_parts: list[str] = []
    if trailing_pe is not None:
        ratio_parts.append(f"PE(TTM) {_fmt_ratio(trailing_pe)}")
    elif forward_pe is not None:
        ratio_parts.append(f"PE(FWD) {_fmt_ratio(forward_pe)}")
    if peg is not None:
        ratio_parts.append(f"PEG {_fmt_ratio(peg)}")
    if roe is not None:
        ratio_parts.append(f"ROE {_fmt_ratio(roe, pct=True)}")
    if roce is not None:
        ratio_parts.append(f"ROCE {_fmt_ratio(roce, pct=True)}")
    if fcf is not None:
        ratio_parts.append(f"FCF {fmt_compact_num(fcf)}")
    if ratio_parts:
        print(" | ".join(ratio_parts))

    if include_after_hours:
        post = info.get("postMarketPrice")
        pre = info.get("preMarketPrice")
        if post is not None or pre is not None:
            post_txt = fmt_price(post) if post is not None else "n/a"
            pre_txt = fmt_price(pre) if pre is not None else "n/a"
            print(f"Ext Pre {pre_txt}  Post {post_txt}")
    print()
    return 0
