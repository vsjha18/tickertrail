from __future__ import annotations

import datetime as dt
import io
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from typing import Any, Callable

import pandas as pd


def fetch_day_range_fallback(
    symbol: str,
    download_fn: Callable[..., pd.DataFrame],
    track_network_call: Callable[[str], None],
) -> tuple[float | None, float | None]:
    """Best-effort fallback to derive day low/high from intraday history."""
    try:
        track_network_call("yfinance.download")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            df = download_fn(symbol, period="1d", interval="1m", progress=False, auto_adjust=False)
        if df.empty:
            return None, None
        lows = df["Low"]
        highs = df["High"]
        if hasattr(lows, "columns"):
            lows = lows.iloc[:, 0]
        if hasattr(highs, "columns"):
            highs = highs.iloc[:, 0]
        low_v = float(min(lows.tolist()))
        high_v = float(max(highs.tolist()))
        if high_v <= low_v:
            return None, None
        return low_v, high_v
    except Exception:
        return None, None


def fetch_day_range_fallback_candidates(
    symbols: list[str],
    fetch_day_range_fallback_fn: Callable[[str], tuple[float | None, float | None]],
) -> tuple[float | None, float | None]:
    """Try intraday day-range derivation over ordered symbol candidates."""
    seen: set[str] = set()
    for symbol in symbols:
        candidate = symbol.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        low_f, high_f = fetch_day_range_fallback_fn(candidate)
        if low_f is not None and high_f is not None and high_f > low_f:
            return low_f, high_f
    return None, None


def series_for_symbol_field(df: pd.DataFrame, symbol: str, field: str) -> pd.Series | None:
    """Extract one symbol+field series from yfinance batch output."""
    if df.empty:
        return None
    try:
        if isinstance(df.columns, pd.MultiIndex):
            top_level_columns = set(df.columns.get_level_values(0))
            if symbol in top_level_columns:
                series = df[symbol][field]
            elif field in top_level_columns:
                series = df[field][symbol]
            else:
                return None
        else:
            if field not in df.columns:
                return None
            series = df[field]
        cleaned = pd.to_numeric(series, errors="coerce").dropna()
        return cleaned if not cleaned.empty else None
    except Exception:
        return None


def has_usable_day_range(snapshot: dict[str, float | None]) -> bool:
    """Return True when a snapshot already has a valid day low/high pair."""
    low = snapshot.get("regularMarketDayLow")
    high = snapshot.get("regularMarketDayHigh")
    try:
        return low is not None and high is not None and float(high) > float(low)
    except (TypeError, ValueError):
        return False


def coerce_float(value: Any) -> float | None:
    """Convert a scalar-like value to float, returning None on parse failures."""
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def coerce_epoch_seconds(value: Any) -> float | None:
    """Convert a datetime-like or numeric timestamp payload to epoch seconds."""
    try:
        if value is None:
            return None
        if isinstance(value, dt.datetime):
            stamp = value
        elif hasattr(value, "to_pydatetime"):
            stamp = value.to_pydatetime()
        elif isinstance(value, (int, float)):
            return float(value)
        else:
            return None
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=dt.timezone.utc)
        return float(stamp.timestamp())
    except Exception:
        return None


def parse_day_range_text(value: Any) -> tuple[float | None, float | None]:
    """Parse textual day-range payloads like '31800.0 - 32100.5'."""
    text = str(value).strip() if value is not None else ""
    if not text:
        return None, None
    if " - " in text:
        left, right = text.split(" - ", 1)
    elif "-" in text:
        left, right = text.split("-", 1)
    else:
        return None, None
    low = coerce_float(left.strip())
    high = coerce_float(right.strip())
    if low is None or high is None or high <= low:
        return None, None
    return low, high


def extract_quote_day_range(info: dict[str, Any]) -> tuple[float | None, float | None]:
    """Extract day low/high from quote payload across known Yahoo key variants."""
    day_low = coerce_float(
        info.get("regularMarketDayLow")
        if info.get("regularMarketDayLow") is not None
        else info.get("dayLow")
    )
    day_high = coerce_float(
        info.get("regularMarketDayHigh")
        if info.get("regularMarketDayHigh") is not None
        else info.get("dayHigh")
    )
    if day_low is not None and day_high is not None and day_high > day_low:
        return day_low, day_high
    low_txt, high_txt = parse_day_range_text(
        info.get("regularMarketDayRange")
        if info.get("regularMarketDayRange") is not None
        else info.get("dayRange")
    )
    if low_txt is not None and high_txt is not None and high_txt > low_txt:
        return low_txt, high_txt
    return None, None


def enrich_snapshot_day_range_from_quote(
    symbol: str,
    snapshot: dict[str, float | None],
    get_quote_payload: Callable[[str], dict[str, Any]],
) -> None:
    """Fill missing day low/high from quote payload when price exists."""
    if snapshot.get("regularMarketPrice") is None:
        return
    if has_usable_day_range(snapshot):
        return
    info = get_quote_payload(symbol)
    day_low, day_high = extract_quote_day_range(info)
    if day_low is None or day_high is None or day_high <= day_low:
        return
    snapshot["regularMarketDayLow"] = day_low
    snapshot["regularMarketDayHigh"] = day_high


def enrich_snapshot_day_range_from_symbol_candidates(
    symbols: list[str],
    snapshot: dict[str, float | None],
    enrich_from_quote_fn: Callable[[str, dict[str, float | None]], None],
) -> None:
    """Fill missing day range by probing quote payloads in ordered symbol priority."""
    seen: set[str] = set()
    for symbol in symbols:
        candidate = symbol.strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if has_usable_day_range(snapshot):
            return
        enrich_from_quote_fn(candidate, snapshot)


def batch_index_snapshots(
    symbols: list[str],
    download_fn: Callable[..., pd.DataFrame],
    track_network_call: Callable[[str], None],
) -> dict[str, dict[str, float | None]]:
    """Fetch grouped snapshots using minute bars with daily-close fallback."""
    snapshots: dict[str, dict[str, float | None]] = {
        sym: {
            "regularMarketPrice": None,
            "regularMarketPreviousClose": None,
            "regularMarketDayLow": None,
            "regularMarketDayHigh": None,
            "regularMarketChange": None,
            "regularMarketChangePercent": None,
            "marketDataTimestamp": None,
            "marketDataIsIntraday": None,
        }
        for sym in symbols
    }
    if not symbols:
        return snapshots
    symbol_str = " ".join(symbols)
    daily = pd.DataFrame()
    intraday = pd.DataFrame()

    try:
        track_network_call("yfinance.download")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            daily = download_fn(symbol_str, period="5d", interval="1d", progress=False, auto_adjust=False)
    except Exception:
        daily = pd.DataFrame()

    try:
        track_network_call("yfinance.download")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            intraday = download_fn(symbol_str, period="1d", interval="1m", progress=False, auto_adjust=False)
    except Exception:
        intraday = pd.DataFrame()

    if daily.empty and intraday.empty:
        return snapshots

    for symbol in symbols:
        close_series = series_for_symbol_field(daily, symbol, "Close")
        intraday_close_series = series_for_symbol_field(intraday, symbol, "Close")
        intraday_low_series = series_for_symbol_field(intraday, symbol, "Low")
        intraday_high_series = series_for_symbol_field(intraday, symbol, "High")
        daily_low_series = series_for_symbol_field(daily, symbol, "Low")
        daily_high_series = series_for_symbol_field(daily, symbol, "High")
        if close_series is None and intraday_close_series is None:
            continue

        if intraday_close_series is not None and len(intraday_close_series) >= 1:
            price = float(intraday_close_series.iloc[-1])
            timestamp = coerce_epoch_seconds(intraday_close_series.index[-1])
            is_intraday = 1.0
        elif close_series is not None and len(close_series) >= 1:
            price = float(close_series.iloc[-1])
            timestamp = coerce_epoch_seconds(close_series.index[-1])
            is_intraday = 0.0
        else:
            price = None
            timestamp = None
            is_intraday = None

        prev = float(close_series.iloc[-2]) if close_series is not None and len(close_series) >= 2 else None

        if intraday_low_series is not None and len(intraday_low_series) >= 1:
            day_low = float(min(intraday_low_series.tolist()))
        elif daily_low_series is not None and len(daily_low_series) >= 1:
            day_low = float(daily_low_series.iloc[-1])
        else:
            day_low = None

        if intraday_high_series is not None and len(intraday_high_series) >= 1:
            day_high = float(max(intraday_high_series.tolist()))
        elif daily_high_series is not None and len(daily_high_series) >= 1:
            day_high = float(daily_high_series.iloc[-1])
        else:
            day_high = None

        change = None if price is None or prev is None else price - prev
        change_pct = None if change is None or not prev else (change / prev) * 100
        snapshots[symbol] = {
            "regularMarketPrice": price,
            "regularMarketPreviousClose": prev,
            "regularMarketDayLow": day_low,
            "regularMarketDayHigh": day_high,
            "regularMarketChange": change,
            "regularMarketChangePercent": change_pct,
            "marketDataTimestamp": timestamp,
            "marketDataIsIntraday": is_intraday,
        }
    return snapshots


def resolve_group_candidate_snapshots(
    candidate_map: dict[str, list[str]],
    batch_index_snapshots_fn: Callable[[list[str]], dict[str, dict[str, float | None]]],
    enrich_day_range_from_symbol_candidates_fn: Callable[[list[str], dict[str, float | None]], None],
    progress_scope: Callable[[str], contextmanager[None]],
) -> tuple[dict[str, tuple[str, dict[str, float | None]]], int]:
    """Resolve per-key snapshot via repeated batch passes over ordered candidates."""
    chosen: dict[str, tuple[str, dict[str, float | None]]] = {}
    if not candidate_map:
        return chosen, 0

    unresolved = {key: [candidate for candidate in candidates if candidate] for key, candidates in candidate_map.items()}
    all_candidates = sorted({symbol for candidates in unresolved.values() for symbol in candidates})
    snapshots: dict[str, dict[str, float | None]] = {}
    passes_used = 0

    def _promote_resolved() -> None:
        """Select the first candidate with usable snapshot for each unresolved key."""
        for key, candidates in unresolved.items():
            if key in chosen:
                continue
            for symbol in candidates:
                snap = snapshots.get(symbol)
                if snap is None or snap.get("regularMarketPrice") is None:
                    continue
                chosen[key] = (symbol, snap)
                break

    def _missing_batch_symbols() -> list[str]:
        """Return symbols still needed to resolve unresolved keys."""
        needed: set[str] = set()
        for key, candidates in unresolved.items():
            if key in chosen:
                continue
            for symbol in candidates:
                snap = snapshots.get(symbol)
                if snap is None or snap.get("regularMarketPrice") is None:
                    needed.add(symbol)
        return sorted(needed)

    with progress_scope("Resolving index board"):
        for pass_idx in range(3):
            to_fetch = all_candidates if pass_idx == 0 else _missing_batch_symbols()
            if not to_fetch:
                break
            snapshots.update(batch_index_snapshots_fn(to_fetch))
            passes_used = pass_idx + 1
            _promote_resolved()
            if len(chosen) == len(candidate_map):
                break

        for key, (chosen_symbol, snapshot) in list(chosen.items()):
            enrich_day_range_from_symbol_candidates_fn(unresolved.get(key, [chosen_symbol]), snapshot)

    return chosen, passes_used


def fetch_group_snapshots_with_retries(
    symbols: list[str],
    batch_index_snapshots_fn: Callable[[list[str]], dict[str, dict[str, float | None]]],
    enrich_day_range_from_symbol_candidates_fn: Callable[[list[str], dict[str, float | None]], None],
    progress_scope: Callable[[str], contextmanager[None]],
) -> tuple[dict[str, dict[str, float | None]], int]:
    """Fetch grouped snapshots with repeated batch retries over missing symbols."""
    snapshots: dict[str, dict[str, float | None]] = {}
    if not symbols:
        return snapshots, 0
    passes_used = 0
    missing = list(dict.fromkeys(symbols))

    def _missing_symbols(current: dict[str, dict[str, float | None]], requested: list[str]) -> list[str]:
        """Compute which requested symbols still lack usable price."""
        return [sym for sym in requested if current.get(sym, {}).get("regularMarketPrice") is None]

    with progress_scope("Resolving snap rows"):
        for pass_idx in range(3):
            if not missing:
                break
            fetched = batch_index_snapshots_fn(missing)
            snapshots.update(fetched)
            passes_used = pass_idx + 1
            missing = _missing_symbols(snapshots, missing)

        for sym, snapshot in snapshots.items():
            enrich_day_range_from_symbol_candidates_fn([sym], snapshot)

    return snapshots, passes_used
