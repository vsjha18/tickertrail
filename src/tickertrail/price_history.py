from __future__ import annotations

import datetime as dt
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Callable

from . import timeframe


def _is_repo_root(candidate: Path) -> bool:
    """Return true when a path looks like the tickertrail repository root."""
    return (candidate / "pyproject.toml").is_file() and (candidate / "src" / "tickertrail").is_dir()


def _resolve_cache_dir(module_file: Path | None = None, cwd: Path | None = None) -> Path:
    """Resolve the daily history cache directory anchored at repository root."""
    current = (cwd or Path.cwd()).resolve()
    # Prefer the active working tree so CLI runs from this repo always use local `.cache/history`.
    for candidate in (current, *current.parents):
        if _is_repo_root(candidate):
            return candidate / ".cache" / "history"

    module_path = (module_file or Path(__file__)).resolve()
    module_root = module_path.parents[2]
    if _is_repo_root(module_root):
        return module_root / ".cache" / "history"

    # Keep fallback local to process cwd to avoid writing into unrelated global locations.
    return current / ".cache" / "history"


_CACHE_DIR = _resolve_cache_dir()
_CACHE_DAY: str | None = None
_CACHE_STORE: dict[str, dict[str, Any]] | None = None
_CACHE_METRICS: dict[str, int] = {"hits": 0, "misses": 0}


def _cache_now() -> dt.datetime:
    """Return local wall-clock timestamp used for cache freshness checks."""
    return dt.datetime.now()


def reset_cache_metrics() -> None:
    """Reset per-command cache hit/miss counters."""
    _CACHE_METRICS["hits"] = 0
    _CACHE_METRICS["misses"] = 0


def cache_metrics_snapshot() -> dict[str, int]:
    """Return a copy of cache metrics for footer reporting."""
    return {"hits": _CACHE_METRICS["hits"], "misses": _CACHE_METRICS["misses"]}


def _cache_day() -> str:
    """Return the active cache day token (YYYY-MM-DD) in local time."""
    return dt.date.today().isoformat()


def _cache_path_for_day(day: str) -> Path:
    """Return cache file path for one day token."""
    return _CACHE_DIR / f"{day}.json"


def _cache_refresh_day() -> None:
    """Rotate in-memory cache when local day changes and load today's file."""
    global _CACHE_DAY, _CACHE_STORE
    day = _cache_day()
    if _CACHE_DAY == day and _CACHE_STORE is not None:
        return
    _CACHE_DAY = day
    _CACHE_STORE = {}
    path = _cache_path_for_day(day)
    if not path.exists():
        return
    try:
        with path.open(encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            for key, value in payload.items():
                if isinstance(key, str) and isinstance(value, dict):
                    _CACHE_STORE[key] = value
    except (OSError, json.JSONDecodeError):
        _CACHE_STORE = {}


def _cache_key(kind: str, symbol: str, period_token: str, interval: str) -> str:
    """Build a deterministic cache key for one history request."""
    return "|".join([kind, symbol.strip().upper(), period_token.strip().lower(), interval.strip().lower()])


def _cache_get(kind: str, symbol: str, period_token: str, interval: str) -> dict[str, Any] | None:
    """Get one cached history payload for today."""
    _cache_refresh_day()
    assert _CACHE_STORE is not None
    value = _CACHE_STORE.get(_cache_key(kind, symbol, period_token, interval))
    if isinstance(value, dict):
        _CACHE_METRICS["hits"] += 1
        return value
    _CACHE_METRICS["misses"] += 1
    return None


def _cache_set(kind: str, symbol: str, period_token: str, interval: str, payload: dict[str, Any]) -> None:
    """Set one cached history payload for today and persist it to disk."""
    _cache_refresh_day()
    assert _CACHE_STORE is not None
    record = dict(payload)
    record["_cached_at"] = _cache_now().isoformat()
    _CACHE_STORE[_cache_key(kind, symbol, period_token, interval)] = record
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _cache_path_for_day(_CACHE_DAY or _cache_day())
        tmp_path = path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(_CACHE_STORE, f, ensure_ascii=True, separators=(",", ":"))
            f.write("\n")
        tmp_path.replace(path)
    except OSError:
        return


def clear_history_cache_today() -> bool:
    """Delete today's history cache (memory + disk)."""
    global _CACHE_DAY, _CACHE_STORE
    day = _cache_day()
    _CACHE_DAY = day
    _CACHE_STORE = {}
    path = _cache_path_for_day(day)
    if not path.exists():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def history_cache_summary_today() -> dict[str, Any]:
    """Return a structured summary of today's persisted history cache contents."""
    _cache_refresh_day()
    assert _CACHE_STORE is not None
    day = _CACHE_DAY or _cache_day()
    path = _cache_path_for_day(day)
    kinds: dict[str, int] = {}
    symbols: set[str] = set()
    periods: set[str] = set()
    intervals: set[str] = set()
    parsed_entries = 0

    for key in _CACHE_STORE:
        parts = key.split("|")
        if len(parts) != 4:
            continue
        kind, symbol, period_token, interval = parts
        parsed_entries += 1
        kinds[kind] = kinds.get(kind, 0) + 1
        symbols.add(symbol)
        periods.add(period_token)
        intervals.add(interval)

    return {
        "day": day,
        "path": str(path),
        "file_exists": path.exists(),
        "file_size_bytes": (path.stat().st_size if path.exists() else 0),
        "entries_total": len(_CACHE_STORE),
        "entries_parsed": parsed_entries,
        "kinds": kinds,
        "symbols": sorted(symbols),
        "periods": sorted(periods),
        "intervals": sorted(intervals),
    }


def _intraday_close_points_ttl_seconds(period_token: str, interval: str) -> int | None:
    """Return TTL seconds for intraday close-point cache keys, else None."""
    token = period_token.strip().lower()
    interval_norm = interval.strip().lower()
    if token != "1d":
        return None
    ttl_by_interval = {
        "1m": 60,
        "2m": 120,
        "5m": 120,
        "15m": 300,
        "30m": 300,
        "60m": 600,
        "90m": 900,
        "1h": 600,
    }
    return ttl_by_interval.get(interval_norm)


def _cache_record_is_fresh(payload: dict[str, Any], ttl_seconds: int | None) -> bool:
    """Return true when payload age is within TTL; no TTL means always fresh."""
    if ttl_seconds is None:
        return True
    raw_cached_at = payload.get("_cached_at")
    if not isinstance(raw_cached_at, str):
        return False
    try:
        cached_at = dt.datetime.fromisoformat(raw_cached_at)
    except ValueError:
        return False
    age_seconds = (_cache_now() - cached_at).total_seconds()
    return age_seconds <= ttl_seconds


def fetch_close_points_for_token(
    symbol: str,
    period_token: str,
    interval: str,
    download_fn: Callable[..., Any],
    track_network_call: Callable[[str], None],
) -> tuple[list[dt.datetime], list[float]]:
    """Download close-price points for a normalized period token and interval."""
    token = timeframe.normalize_period_token(period_token)
    if token is None:
        return [], []

    cached = _cache_get("close_points", symbol, token, interval)
    ttl_seconds = _intraday_close_points_ttl_seconds(token, interval)
    if cached is not None and _cache_record_is_fresh(cached, ttl_seconds):
        raw_points = cached.get("points")
        raw_prices = cached.get("prices")
        if isinstance(raw_points, list) and isinstance(raw_prices, list) and len(raw_points) == len(raw_prices):
            points: list[dt.datetime] = []
            prices: list[float] = []
            try:
                for point_raw, price_raw in zip(raw_points, raw_prices):
                    if not isinstance(point_raw, str):
                        raise ValueError("invalid point")
                    points.append(dt.datetime.fromisoformat(point_raw))
                    prices.append(float(price_raw))
                return points, prices
            except (TypeError, ValueError):
                pass

    # Use direct period fetch when Yahoo supports it; otherwise build explicit start/end.
    if token in ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max"):
        track_network_call("yfinance.download")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            df = download_fn(symbol, period=token, interval=interval, progress=False, auto_adjust=True)
    else:
        days = timeframe.period_token_days(token)
        if days is None:
            return [], []
        end_dt = dt.datetime.now() + dt.timedelta(days=1)
        start_dt = end_dt - dt.timedelta(days=days)
        track_network_call("yfinance.download")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            df = download_fn(
                symbol,
                start=start_dt.strftime("%Y-%m-%d"),
                end=end_dt.strftime("%Y-%m-%d"),
                interval=interval,
                progress=False,
                auto_adjust=True,
            )
    if df.empty:
        return [], []

    close = df["Close"]
    if hasattr(close, "columns"):
        close = close.iloc[:, 0]
    idx = [i.to_pydatetime() for i in close.index]
    prices = [float(v) for v in close.tolist()]
    _cache_set(
        "close_points",
        symbol,
        token,
        interval,
        {
            "points": [point.isoformat() for point in idx],
            "prices": prices,
        },
    )
    return idx, prices


def fetch_daily_ohlcv_for_period(
    symbol: str,
    period_token: str,
    download_fn: Callable[..., Any],
    track_network_call: Callable[[str], None],
) -> tuple[list[dt.datetime], list[float], list[float | None], list[float | None], list[float | None]]:
    """Download daily OHLCV-like arrays for one symbol and normalized period token."""
    token = timeframe.normalize_period_token(period_token)
    if token is None:
        return [], [], [], [], []

    cached = _cache_get("daily_ohlcv", symbol, token, "1d")
    if cached is not None:
        raw_points = cached.get("points")
        raw_close = cached.get("close")
        raw_high = cached.get("high")
        raw_low = cached.get("low")
        raw_volume = cached.get("volume")
        if (
            isinstance(raw_points, list)
            and isinstance(raw_close, list)
            and isinstance(raw_high, list)
            and isinstance(raw_low, list)
            and isinstance(raw_volume, list)
        ):
            size = len(raw_points)
            if len(raw_close) == size and len(raw_high) == size and len(raw_low) == size and len(raw_volume) == size:
                try:
                    points = [dt.datetime.fromisoformat(value) for value in raw_points]
                    close = [float(value) if value is not None else None for value in raw_close]
                    high = [float(value) if value is not None else None for value in raw_high]
                    low = [float(value) if value is not None else None for value in raw_low]
                    volume = [float(value) if value is not None else None for value in raw_volume]
                    return points, close, high, low, volume
                except (TypeError, ValueError):
                    pass

    # Quote analytics need one daily payload that multiple signals can reuse.
    track_network_call("yfinance.download")
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        df = download_fn(symbol, period=token, interval="1d", progress=False, auto_adjust=True)
    if df.empty:
        return [], [], [], [], []

    def _series_values(field: str) -> list[float | None]:
        """Extract one column as floats while preserving row count alignment."""
        if field not in df.columns:
            return [None] * len(df.index)
        series = df[field]
        if hasattr(series, "columns"):
            series = series.iloc[:, 0]
        out: list[float | None] = []
        for value in series.tolist():
            try:
                out.append(float(value))
            except (TypeError, ValueError):
                out.append(None)
        return out

    close = _series_values("Close")
    high = _series_values("High")
    low = _series_values("Low")
    volume = _series_values("Volume")
    idx = [i.to_pydatetime() for i in df.index]
    _cache_set(
        "daily_ohlcv",
        symbol,
        token,
        "1d",
        {
            "points": [point.isoformat() for point in idx],
            "close": close,
            "high": high,
            "low": low,
            "volume": volume,
        },
    )
    return idx, close, high, low, volume
