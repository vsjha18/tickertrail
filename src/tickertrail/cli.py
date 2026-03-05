from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import random
import re
import shutil
import subprocess
import sys
import textwrap
import time
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Callable
from zoneinfo import ZoneInfo

import pandas as pd
import plotext as plt
import yfinance as yf

from . import market_hours
from . import price_history
from . import quote_tools
from . import snapshot_service
from . import timeframe
from . import views

_PERIODS = ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max")
_INTERVALS = ("1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo")
_NSE_UNIVERSE_CSV = Path(__file__).resolve().parents[2] / "data" / "nse_equity_list.csv"
_INDEX_CONSTITUENTS_CSV = Path(__file__).resolve().parents[2] / "data" / "index_constituents.csv"
_WATCHLIST_DB_JSON = Path(__file__).resolve().parents[2] / "data" / "db.json"
_HISTORY_FILE = Path(__file__).resolve().parents[2] / ".tickertrail_history"
_CLI_CONF_JSON = Path(__file__).resolve().with_name("conf.json")
_INDEX_SYMBOL_FALLBACKS: dict[str, tuple[str, ...]] = {
    # Keep only empirically useful Yahoo alternates to minimize dead probes.
    "^CNXMIDCAP": ("NIFTY_MIDCAP_100.NS",),
    "^NIFTYNXT50": ("NIFTY_NEXT_50.NS",),
    "^NSESMCP100": ("NIFTY_SMLCAP_100.NS",),
    "^CNXDEFENCE": ("NIFTY_IND_DEFENCE.NS",),
}
_INDEX_PREFERRED_QUOTE_SYMBOLS: dict[str, str] = {
    "^CNXMIDCAP": "NIFTY_MIDCAP_100.NS",
    "^NIFTYNXT50": "NIFTY_NEXT_50.NS",
    "^NSESMCP100": "NIFTY_SMLCAP_100.NS",
    "^CNXDEFENCE": "NIFTY_IND_DEFENCE.NS",
}
_INDEX_NORMALIZATION_ALIASES: dict[str, str] = {
    # Compatibility aliases retained for normalization only (not active probe targets).
    "^NSEMDCP100": "^CNXMIDCAP",
    "NIFTYMIDCAP100.NS": "^CNXMIDCAP",
    "^NSESMCP250": "^NSESMCP100",
    "NIFTY_SMALLCAP_100.NS": "^NSESMCP100",
    "NIFTY_IND_DEFENCE.NS": "^CNXDEFENCE",
}
_INDIA_INDEX_BOARD = (
    ("^NSEI", "NIFTY 50"),
    ("^NSEBANK", "NIFTY BANK"),
    ("^CNXIT", "NIFTY IT"),
    ("^CNXMIDCAP", "NIFTY MIDCAP 100"),
    ("^NSEMDCP50", "NIFTY MIDCAP SELECT"),
    ("^NIFTYNXT50", "NIFTY NEXT 50"),
    ("^CNXINFRA", "NIFTY INFRA"),
    ("^CNXPSE", "NIFTY PSE"),
    ("^CNXAUTO", "NIFTY AUTO"),
    ("^CNXENERGY", "NIFTY ENERGY"),
    ("^CNXDEFENCE", "NIFTY DEFENCE"),
    ("^CNXFMCG", "NIFTY FMCG"),
    ("^CNXMEDIA", "NIFTY MEDIA"),
    ("^CNXMETAL", "NIFTY METAL"),
    ("^CNXMNC", "NIFTY MNC"),
    ("^CNXPHARMA", "NIFTY PHARMA"),
    ("^CNXPSUBANK", "NIFTY PSU BANK"),
    ("^CNXREALTY", "NIFTY REALTY"),
    ("NIFTY_FIN_SERVICE.NS", "NIFTY FIN SERVICE"),
    ("^CNXCONSUM", "NIFTY CONSUMPTION"),
    ("^INDIAVIX", "INDIA VIX"),
    ("^NSESMCP100", "NIFTY SMALLCAP 100"),
)
_GLOBAL_INDEX_BOARD = (
    ("^FTSE", "FTSE 100"),
    ("^FCHI", "CAC 40"),
    ("^HSI", "HANG SENG"),
    ("^N225", "NIKKEI 225"),
    ("^IXIC", "NASDAQ"),
    ("^DJI", "DOW JONES"),
)
_INDEX_ALIASES = {
    # India indices
    "NIFTY": "^NSEI",
    "NIFTY50": "^NSEI",
    "NIFTY 50": "^NSEI",
    "NIFTYBANK": "^NSEBANK",
    "NIFTY BANK": "^NSEBANK",
    "BANKNIFTY": "^NSEBANK",
    "NSEBANK": "^NSEBANK",
    "BANK": "^NSEBANK",
    "MIDCAP": "^CNXMIDCAP",
    "MIDCAP100": "^CNXMIDCAP",
    "NIFTYMIDCAP100": "^CNXMIDCAP",
    "NIFTY MIDCAP 100": "^CNXMIDCAP",
    "MIDCAPSELECT": "^NSEMDCP50",
    "MIDCAP SELECT": "^NSEMDCP50",
    "NIFTYMIDCAPSELECT": "^NSEMDCP50",
    "NIFTY MIDCAP SELECT": "^NSEMDCP50",
    "MID SELECT": "^NSEMDCP50",
    "SELECT": "^NSEMDCP50",
    "SMALLCAP": "^NSESMCP100",
    "SMALLCAP100": "^NSESMCP100",
    "NIFTYSMALLCAP100": "^NSESMCP100",
    "NIFTY SMALLCAP 100": "^NSESMCP100",
    "VIX": "^INDIAVIX",
    "INDIAVIX": "^INDIAVIX",
    "INDIA VIX": "^INDIAVIX",
    "NIFTY IT": "^CNXIT",
    "NIFTYIT": "^CNXIT",
    "IT": "^CNXIT",
    "FINNIFTY": "NIFTY_FIN_SERVICE.NS",
    "NIFTYFIN": "NIFTY_FIN_SERVICE.NS",
    "NIFTY FIN SERVICE": "NIFTY_FIN_SERVICE.NS",
    "NIFTYFINSERVICE": "NIFTY_FIN_SERVICE.NS",
    "NIFTY FINANCE": "NIFTY_FIN_SERVICE.NS",
    "NIFTYFINANCE": "NIFTY_FIN_SERVICE.NS",
    "FIN": "NIFTY_FIN_SERVICE.NS",
    "FINANCE": "NIFTY_FIN_SERVICE.NS",
    "NIFTYFMCG": "^CNXFMCG",
    "NIFTY FMCG": "^CNXFMCG",
    "FMCG": "^CNXFMCG",
    "NIFTYPSE": "^CNXPSE",
    "NIFTY PSE": "^CNXPSE",
    "PSE": "^CNXPSE",
    "CPSE": "^CNXPSE",
    "NIFTYAUTO": "^CNXAUTO",
    "NIFTY AUTO": "^CNXAUTO",
    "AUTO": "^CNXAUTO",
    "NIFTYINFRA": "^CNXINFRA",
    "NIFTY INFRA": "^CNXINFRA",
    "INFRA": "^CNXINFRA",
    "NIFTYENERGY": "^CNXENERGY",
    "NIFTY ENERGY": "^CNXENERGY",
    "ENERGY": "^CNXENERGY",
    "NIFTYMEDIA": "^CNXMEDIA",
    "NIFTY MEDIA": "^CNXMEDIA",
    "MEDIA": "^CNXMEDIA",
    "NIFTYMETAL": "^CNXMETAL",
    "NIFTY METAL": "^CNXMETAL",
    "METAL": "^CNXMETAL",
    "METALS": "^CNXMETAL",
    "NIFTYMNC": "^CNXMNC",
    "NIFTY MNC": "^CNXMNC",
    "MNC": "^CNXMNC",
    "NIFTYREALTY": "^CNXREALTY",
    "NIFTY REALTY": "^CNXREALTY",
    "REALTY": "^CNXREALTY",
    "NIFTYPHARMA": "^CNXPHARMA",
    "NIFTY PHARMA": "^CNXPHARMA",
    "PHARMA": "^CNXPHARMA",
    "NIFTYCONSUMPTION": "^CNXCONSUM",
    "NIFTY CONSUMPTION": "^CNXCONSUM",
    "NIFTYCONSUMER": "^CNXCONSUM",
    "NIFTY CONSUMER": "^CNXCONSUM",
    "CONSUMPTION": "^CNXCONSUM",
    "CONSUMER": "^CNXCONSUM",
    "CONSUMERS": "^CNXCONSUM",
    "NEXT50": "^NIFTYNXT50",
    "NIFTYNEXT50": "^NIFTYNXT50",
    "NIFTY NEXT 50": "^NIFTYNXT50",
    "NIFTYDEFENCE": "^CNXDEFENCE",
    "NIFTY DEFENCE": "^CNXDEFENCE",
    "NIFTYDEFENSE": "^CNXDEFENCE",
    "NIFTY DEFENSE": "^CNXDEFENCE",
    "DEFENCE": "^CNXDEFENCE",
    "DEFENSE": "^CNXDEFENCE",
    "PSUBANK": "^CNXPSUBANK",
    "NIFTYPSUBANK": "^CNXPSUBANK",
    "NIFTY PSU BANK": "^CNXPSUBANK",
    "PSU": "^CNXPSUBANK",
    "SENSEX": "^BSESN",
    "BSE SENSEX": "^BSESN",
    # Global indices
    "NASDAQ": "^IXIC",
    "NASADQ": "^IXIC",
    "DOW": "^DJI",
    "DOWJONES": "^DJI",
    "HANGSENG": "^HSI",
    "HANG SENG": "^HSI",
    "NIKKEI": "^N225",
    "NIKKEI225": "^N225",
    "FTSE": "^FTSE",
    "FTSE100": "^FTSE",
    "FTSE 100": "^FTSE",
    "SP": "^GSPC",
    "S&P": "^GSPC",
    "S&P500": "^GSPC",
    "SP500": "^GSPC",
}
_NSE_UNIVERSE_CACHE: list[dict[str, str]] | None = None
_SNAP_UNIVERSE_CACHE: dict[str, tuple[str, tuple[str, ...]]] | None = None
_INTRADAY_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h"}
_REPL_INTRADAY_INTERVAL_ALIASES: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "1hr": "1h",
}
_NETWORK_CALL_COUNTS: dict[str, int] = {}
_PROGRESS_STATE: dict[str, Any] = {"active": False, "emitted": False}
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
_INDEX_EXPECTED_CONSTITUENT_COUNTS: dict[str, int] = {
    "^NSEI": 50,
    "^NIFTYNXT50": 50,
    "^CNXMIDCAP": 100,
    "^NSEMDCP50": 25,
    "^NSESMCP100": 100,
    "^FTSE": 100,
    "^FCHI": 40,
    "^N225": 225,
    "^DJI": 30,
}
_SNAP_ALLOWED_INDEX_SYMBOLS: set[str] = {
    *(symbol for symbol, _label in _INDIA_INDEX_BOARD if symbol != "^INDIAVIX"),
    "^DJI",
}
_MOVES_DAYS_BY_PERIOD: dict[str, int] = {
    "7d": 7,
    "1mo": 30,
    "3mo": 90,
    "6mo": 180,
    "9mo": 270,
    "1y": 365,
}
_ANALYTICS_PERIOD_HINT = "Nd|Nmo(<12)|Ny"
_RUNTIME_CONFIG_CACHE: dict[str, float] | None = None
_INDEX_BOARD_SYMBOLS: set[str] = {*(symbol.upper() for symbol, _ in _INDIA_INDEX_BOARD), *(symbol.upper() for symbol, _ in _GLOBAL_INDEX_BOARD)}


def _read_conf_duration_seconds(payload: dict[str, Any], key: str) -> float:
    """Read one non-negative duration from JSON payload and return seconds.

    Accepted formats:
    - number (treated as seconds)
    - string ending with `ms` (milliseconds)
    - string ending with `s` (seconds)
    """
    raw = payload.get(key)
    if isinstance(raw, (int, float)):
        return max(0.0, float(raw))
    if isinstance(raw, str):
        token = raw.strip().lower()
        try:
            if token.endswith("ms"):
                return max(0.0, float(token[:-2].strip()) / 1000.0)
            if token.endswith("s"):
                return max(0.0, float(token[:-1].strip()))
            return max(0.0, float(token))
        except (TypeError, ValueError):
            return 0.0
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return 0.0


def _load_runtime_config() -> dict[str, float]:
    """Load and cache CLI runtime config from `conf.json` beside `cli.py`."""
    global _RUNTIME_CONFIG_CACHE
    if _RUNTIME_CONFIG_CACHE is not None:
        return _RUNTIME_CONFIG_CACHE
    payload: dict[str, Any] = {}
    try:
        with _CLI_CONF_JSON.open(encoding="utf-8") as f:
            loaded = json.load(f)
            if isinstance(loaded, dict):
                payload = loaded
    except (OSError, json.JSONDecodeError):
        payload = {}

    def _read_with_legacy(primary_key: str, legacy_key: str) -> float:
        """Read config duration by preferred key and fall back to a legacy key."""
        if primary_key in payload:
            return _read_conf_duration_seconds(payload, primary_key)
        return _read_conf_duration_seconds(payload, legacy_key)

    config = {
        "ticker_fallback_jitter_min_s": _read_with_legacy("ticker_fallback_jitter_min", "ticker_fallback_jitter_min_s"),
        "ticker_fallback_jitter_max_s": _read_with_legacy("ticker_fallback_jitter_max", "ticker_fallback_jitter_max_s"),
        "ticker_fallback_backoff_step_s": _read_with_legacy("ticker_fallback_backoff_step", "ticker_fallback_backoff_step_s"),
        "ticker_fallback_backoff_max_s": _read_with_legacy("ticker_fallback_backoff_max", "ticker_fallback_backoff_max_s"),
    }
    if config["ticker_fallback_jitter_max_s"] < config["ticker_fallback_jitter_min_s"]:
        config["ticker_fallback_jitter_max_s"] = config["ticker_fallback_jitter_min_s"]
    _RUNTIME_CONFIG_CACHE = config
    return _RUNTIME_CONFIG_CACHE


@dataclass(frozen=True)
class _ParsedSwingCommand:
    """Parsed form of a swing command (`t` or `c`)."""

    period_token: str = "6mo"
    interval_override: str | None = None
    benchmark_input: str | None = None


@dataclass(frozen=True)
class _ParsedIntradayCommand:
    """Parsed form of an intraday command (`cc`)."""

    interval: str = "5m"
    benchmark_input: str | None = None


@dataclass(frozen=True)
class _ParsedCompareCommand:
    """Parsed form of a multi-instrument compare command (`cmp`)."""

    symbols: tuple[str, ...]
    period_token: str = "6mo"
    interval_override: str | None = None


def _load_watchlists() -> dict[str, list[str]]:
    """Load watchlists from local JSON DB and normalize symbol arrays."""
    try:
        with _WATCHLIST_DB_JSON.open(encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    raw_watchlists = payload.get("watchlists")
    if not isinstance(raw_watchlists, dict):
        return {}

    watchlists: dict[str, list[str]] = {}
    for name, symbols in raw_watchlists.items():
        if not isinstance(name, str) or not isinstance(symbols, list):
            continue
        cleaned_name = name.strip()
        if not cleaned_name:
            continue
        cleaned_symbols: list[str] = []
        for symbol in symbols:
            if not isinstance(symbol, str):
                continue
            token = symbol.strip().upper()
            if token and token not in cleaned_symbols:
                cleaned_symbols.append(token)
        watchlists[cleaned_name] = cleaned_symbols
    return watchlists


def _save_watchlists(watchlists: dict[str, list[str]]) -> None:
    """Persist watchlists to local JSON DB in `data/db.json`."""
    _WATCHLIST_DB_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {"watchlists": watchlists}
    with _WATCHLIST_DB_JSON.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2, sort_keys=True)
        f.write("\n")


def _watchlist_name_valid(name: str) -> bool:
    """Return True when watchlist name is non-empty and uses safe characters."""
    token = name.strip()
    return bool(token) and all(ch.isalnum() or ch in {"-", "_", "."} for ch in token)


def _create_watchlist(name: str) -> tuple[int, str]:
    """Create one watchlist in local DB and return status code/message."""
    cleaned = name.strip()
    if not _watchlist_name_valid(cleaned):
        return 2, "Watchlist name must use letters, digits, '-', '_' or '.'."
    watchlists = _load_watchlists()
    if cleaned in watchlists:
        return 2, f"Watchlist '{cleaned}' already exists."
    watchlists[cleaned] = []
    _save_watchlists(watchlists)
    return 0, f"Watchlist '{cleaned}' created."


def _delete_watchlist(name: str) -> tuple[int, str]:
    """Delete one watchlist from local DB and return status code/message."""
    cleaned = name.strip()
    watchlists = _load_watchlists()
    if cleaned not in watchlists:
        return 2, f"Watchlist '{cleaned}' not found."
    del watchlists[cleaned]
    _save_watchlists(watchlists)
    return 0, f"Watchlist '{cleaned}' deleted."


def _merge_watchlists(source_one: str, source_two: str, target: str) -> tuple[int, str]:
    """Merge two source watchlists into one target watchlist with stable de-dup order."""
    left = source_one.strip()
    right = source_two.strip()
    dst = target.strip()
    if not _watchlist_name_valid(left) or not _watchlist_name_valid(right) or not _watchlist_name_valid(dst):
        return 2, "Watchlist names must use letters, digits, '-', '_' or '.'."

    watchlists = _load_watchlists()
    missing_sources = [name for name in (left, right) if name not in watchlists]
    if missing_sources:
        return 2, f"Watchlist(s) not found: {', '.join(missing_sources)}."

    target_exists = dst in watchlists
    merged_symbols = list(watchlists.get(dst, []))
    seen = set(merged_symbols)
    # Preserve stable insertion order: existing target first, then source_one, then source_two.
    for source_name in (left, right):
        for symbol in watchlists[source_name]:
            if symbol in seen:
                continue
            merged_symbols.append(symbol)
            seen.add(symbol)
    watchlists[dst] = merged_symbols
    _save_watchlists(watchlists)
    action = "updated" if target_exists else "created"
    return 0, f"Watchlist '{dst}' {action} by merging '{left}' + '{right}' ({len(merged_symbols)} symbols)."


def _list_watchlists() -> list[str]:
    """Return sorted watchlist names stored in local DB."""
    return sorted(_load_watchlists().keys(), key=lambda item: item.lower())


def _watchlist_symbols(name: str) -> list[str] | None:
    """Return one watchlist symbol list, or None when not found."""
    return _load_watchlists().get(name.strip())


def _validate_watchlist_symbol(symbol_input: str) -> str | None:
    """Validate one watchlist symbol using local NSE universe data only."""
    token = symbol_input.strip().upper()
    if not token:
        return None
    if token.endswith(".NS"):
        base = token[:-3]
    elif token.endswith(".BO"):
        base = token[:-3]
    else:
        base = token
    if not base:
        return None

    # Keep watchlist add fast and offline by validating against local NSE CSV.
    nse_symbols = {row["symbol"].upper() for row in _load_nse_universe()}
    if base in nse_symbols:
        return f"{base}.NS"
    return None


def _add_symbols_to_watchlist(name: str, symbol_inputs: list[str]) -> tuple[int, list[str], list[str], list[str]]:
    """Validate and add symbols to one watchlist, returning (rc, added, rejected, existing)."""
    watchlists = _load_watchlists()
    cleaned_name = name.strip()
    if cleaned_name not in watchlists:
        return 2, [], symbol_inputs, []

    existing = list(watchlists[cleaned_name])
    existing_set = set(existing)
    added: list[str] = []
    rejected: list[str] = []
    already_present: list[str] = []
    for token in symbol_inputs:
        validated = _validate_watchlist_symbol(token)
        if validated is None:
            rejected.append(token)
            continue
        if validated in existing_set:
            already_present.append(validated)
            continue
        existing.append(validated)
        existing_set.add(validated)
        added.append(validated)
    watchlists[cleaned_name] = existing
    _save_watchlists(watchlists)
    return 0, added, rejected, already_present


def _remove_symbols_from_watchlist(name: str, symbol_inputs: list[str]) -> tuple[int, list[str], list[str]]:
    """Remove symbols from one watchlist, returning (rc, removed, missing)."""
    watchlists = _load_watchlists()
    cleaned_name = name.strip()
    if cleaned_name not in watchlists:
        return 2, [], symbol_inputs

    existing = list(watchlists[cleaned_name])
    existing_set = set(existing)
    removed: list[str] = []
    missing: list[str] = []
    for token in symbol_inputs:
        symbol = token.strip().upper()
        if not symbol:
            continue
        candidates = [symbol]
        if "." not in symbol:
            candidates.extend([f"{symbol}.NS", f"{symbol}.BO"])
        hit = next((candidate for candidate in candidates if candidate in existing_set), None)
        if hit is None:
            missing.append(token)
            continue
        existing_set.remove(hit)
        removed.append(hit)
    watchlists[cleaned_name] = [symbol for symbol in existing if symbol in existing_set]
    _save_watchlists(watchlists)
    return 0, removed, missing


def _reset_network_call_metrics() -> None:
    """Reset per-command network call counters."""
    _NETWORK_CALL_COUNTS.clear()
    price_history.reset_cache_metrics()
    _progress_stop()
    _PROGRESS_STATE["active"] = False
    _PROGRESS_STATE["emitted"] = False


def _track_network_call(api_name: str) -> None:
    """Increment per-command network call counter for one API surface."""
    _NETWORK_CALL_COUNTS[api_name] = _NETWORK_CALL_COUNTS.get(api_name, 0) + 1
    # Keep the activity blip coupled to actual network calls only.
    _progress_tick(blip=True)


def _print_network_call_metrics() -> None:
    """Print per-command network call summary as the final command line."""
    cache_metrics = price_history.cache_metrics_snapshot()
    cache_suffix = f" | cache: hits={cache_metrics['hits']} misses={cache_metrics['misses']}"
    total = sum(_NETWORK_CALL_COUNTS.values())
    if not _NETWORK_CALL_COUNTS:
        print(f"Network calls: 0 [none]{cache_suffix}")
        return
    details = ", ".join(f"{name}={count}" for name, count in sorted(_NETWORK_CALL_COUNTS.items()))
    print(f"Network calls: {total} [{details}]{cache_suffix}")


def _print_history_cache_summary() -> None:
    """Print a compact summary of today's persisted history cache contents."""
    summary = price_history.history_cache_summary_today()
    kinds = dict(summary.get("kinds") or {})
    symbols = list(summary.get("symbols") or [])
    periods = list(summary.get("periods") or [])
    intervals = list(summary.get("intervals") or [])
    entries_total = int(summary.get("entries_total") or 0)
    entries_parsed = int(summary.get("entries_parsed") or 0)
    path = str(summary.get("path") or "n/a")
    file_exists = bool(summary.get("file_exists"))
    file_size = int(summary.get("file_size_bytes") or 0)
    day = str(summary.get("day") or "n/a")

    print("\nHistory Cache Summary")
    print("=====================")
    print(f"Day: {day}")
    print(f"Path: {path}")
    print(f"File: {'present' if file_exists else 'missing'} ({file_size} bytes)")
    print(f"Entries: {entries_total} total ({entries_parsed} parsed keys)")

    if kinds:
        kind_bits = [f"{kind}={count}" for kind, count in sorted(kinds.items())]
        print(f"Kinds: {', '.join(kind_bits)}")
    else:
        print("Kinds: none")

    if symbols:
        shown = ", ".join(symbols[:8])
        suffix = "" if len(symbols) <= 8 else f", ... (+{len(symbols) - 8} more)"
        print(f"Symbols ({len(symbols)}): {shown}{suffix}")
    else:
        print("Symbols: none")

    print(f"Periods: {', '.join(periods) if periods else 'none'}")
    print(f"Intervals: {', '.join(intervals) if intervals else 'none'}")
    print()


def _progress_enabled() -> bool:
    """Return True when lightweight progress rendering should be shown."""
    return bool(getattr(sys.stderr, "isatty", lambda: False)())


def _progress_start(label: str) -> None:
    """Start a transient progress indicator for grouped fetch operations."""
    _ = label
    if not _progress_enabled():
        return
    _PROGRESS_STATE["active"] = True
    _PROGRESS_STATE["emitted"] = False


def _progress_tick(blip: bool = False) -> None:
    """Emit a hash marker when a network call occurs during active grouped fetches."""
    if not _PROGRESS_STATE.get("active") or not _progress_enabled():
        return
    if blip:
        try:
            sys.stderr.write("#")
            sys.stderr.flush()
            _PROGRESS_STATE["emitted"] = True
        except Exception:
            return


def _progress_stop() -> None:
    """Stop and finalize the transient progress indicator."""
    if not _PROGRESS_STATE.get("active"):
        return
    if _progress_enabled() and bool(_PROGRESS_STATE.get("emitted")):
        try:
            sys.stderr.write("\n")
            sys.stderr.flush()
        except Exception:
            pass
    _PROGRESS_STATE["active"] = False
    _PROGRESS_STATE["emitted"] = False


@contextmanager
def _progress_scope(label: str):
    """Context manager for showing progress during grouped network fetches."""
    _progress_start(label)
    try:
        yield
    finally:
        _progress_stop()


@contextmanager
def _silent_progress_scope(_label: str):
    """No-op progress scope used for very small grouped fetches."""
    yield


def _ticker_fallback_pause(consecutive_misses: int) -> None:
    """Throttle per-symbol Ticker fallback calls with jitter and adaptive backoff."""
    config = _load_runtime_config()
    jitter = random.uniform(
        config["ticker_fallback_jitter_min_s"],
        config["ticker_fallback_jitter_max_s"],
    )
    # When misses pile up, progressively cool down to reduce provider throttling.
    backoff_steps = max(0, consecutive_misses // 5)
    backoff = min(
        config["ticker_fallback_backoff_max_s"],
        backoff_steps * config["ticker_fallback_backoff_step_s"],
    )
    time.sleep(jitter + backoff)


def _supports_color() -> bool:
    """Return True when ANSI color output should be enabled."""
    return sys.stdout.isatty() and not bool(__import__("os").environ.get("NO_COLOR"))


def _colorize(text: str, color: str) -> str:
    """Wrap text in ANSI color codes when terminal coloring is enabled."""
    if not _supports_color():
        return text
    codes = {
        "red": "\033[31m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "cyan": "\033[36m",
        "gray": "\033[90m",
    }
    reset = "\033[0m"
    return f"{codes.get(color, '')}{text}{reset}" if color in codes else text


def _color_by_sign(value: float, plus_is_green: bool = True) -> str:
    """Map numeric sign to a semantic color name."""
    if value > 0:
        return "green" if plus_is_green else "red"
    if value < 0:
        return "red" if plus_is_green else "green"
    return "gray"


def _visible_width(text: str) -> int:
    """Return terminal display width for text after stripping ANSI color escapes."""
    return len(_ANSI_ESCAPE_RE.sub("", text))


def _pad_cell(text: str, width: int, align: str = "left") -> str:
    """Pad a string to fixed visible width while preserving embedded ANSI colors."""
    pad = max(0, width - _visible_width(text))
    if align == "right":
        return f"{' ' * pad}{text}"
    return f"{text}{' ' * pad}"


def _range_line(low: float, high: float, current: float, width: int = 36) -> str:
    """Build an ASCII range bar with a marker at the current value."""
    if high <= low:
        return "[n/a]"
    usable = max(10, width)
    pos = int(round((current - low) / (high - low) * (usable - 1)))
    pos = max(0, min(usable - 1, pos))
    chars = ["─"] * usable
    chars[pos] = "●"
    line = "".join(chars)
    return f"[{line}]"


def _build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser for one-shot quote/chart commands."""
    parser = argparse.ArgumentParser(
        prog="tickertrail",
        description="Terminal stock CLI for current quote + historical chart (Yahoo Finance)",
    )
    parser.add_argument("symbol", help="Ticker symbol, e.g. AAPL, MSFT, TSLA")

    subparsers = parser.add_subparsers(dest="command")

    quote_cmd = subparsers.add_parser("quote", help="Show current quote snapshot")
    quote_cmd.add_argument("--no-after-hours", action="store_true", help="Hide pre/post-market data")

    chart_cmd = subparsers.add_parser("chart", help="Render historical close price chart")
    chart_cmd.add_argument("--period", default="6mo", choices=_PERIODS, help="Lookback period")
    chart_cmd.add_argument("--interval", default="1d", choices=_INTERVALS, help="Candle interval")
    chart_cmd.add_argument("--height", type=int, default=22, help="Chart height")
    chart_cmd.add_argument("--width", type=int, default=100, help="Chart width")

    parser.add_argument("--period", default="6mo", choices=_PERIODS, help="Default mode chart period")
    parser.add_argument("--interval", default="1d", choices=_INTERVALS, help="Default mode chart interval")
    parser.add_argument("--height", type=int, default=22, help="Default mode chart height")
    parser.add_argument("--width", type=int, default=100, help="Default mode chart width")
    return parser


def _enable_repl_history() -> None:
    """Enable persistent REPL history when readline is available."""
    try:
        import readline  # type: ignore
    except Exception:
        return

    try:
        if _HISTORY_FILE.exists():
            readline.read_history_file(str(_HISTORY_FILE))
        readline.set_history_length(1000)
        readline.parse_and_bind("tab: complete")
    except Exception:
        return

    import atexit

    def _save() -> None:
        """Persist command history to disk on process exit."""
        try:
            _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            readline.write_history_file(str(_HISTORY_FILE))
        except Exception:
            pass

    atexit.register(_save)


def _fmt_price(value: Any) -> str:
    """Format a numeric price value using two decimals."""
    if value is None:
        return "n/a"
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_change(change: Any, pct: Any) -> str:
    """Format absolute and percent change as a compact signed string."""
    try:
        c = float(change)
        p = float(pct)
    except (TypeError, ValueError):
        return "n/a"
    sign = "+" if c >= 0 else ""
    return f"{sign}{c:.2f} ({sign}{p:.2f}%)"


def _fmt_compact_num(value: Any) -> str:
    """Format large numbers with K/M/B/T suffixes."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return "n/a"
    abs_n = abs(n)
    if abs_n >= 1_000_000_000_000:
        return f"{n/1_000_000_000_000:.2f}T"
    if abs_n >= 1_000_000_000:
        return f"{n/1_000_000_000:.2f}B"
    if abs_n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if abs_n >= 1_000:
        return f"{n/1_000:.2f}K"
    return f"{n:.0f}"


def _get_quote_payload(symbol: str) -> dict[str, Any]:
    """Fetch and normalize quote/fundamental fields from yfinance."""
    _track_network_call("yfinance.Ticker")
    ticker = yf.Ticker(symbol)
    payload: dict[str, Any] = {}

    # `fast_info` is quicker but has fewer keys; merge with full `info` when available.
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            payload.update(dict(ticker.fast_info))
    except Exception:
        pass

    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            payload.update(dict(ticker.info))
    except Exception:
        pass

    if "regularMarketPrice" not in payload and payload.get("lastPrice") is not None:
        payload["regularMarketPrice"] = payload.get("lastPrice")
    if "regularMarketPreviousClose" not in payload and payload.get("previousClose") is not None:
        payload["regularMarketPreviousClose"] = payload.get("previousClose")
    if "regularMarketOpen" not in payload and payload.get("open") is not None:
        payload["regularMarketOpen"] = payload.get("open")
    if "regularMarketDayLow" not in payload and payload.get("dayLow") is not None:
        payload["regularMarketDayLow"] = payload.get("dayLow")
    if "regularMarketDayHigh" not in payload and payload.get("dayHigh") is not None:
        payload["regularMarketDayHigh"] = payload.get("dayHigh")
    if "regularMarketVolume" not in payload and payload.get("volume") is not None:
        payload["regularMarketVolume"] = payload.get("volume")
    return payload


def _candidate_symbols(symbol: str) -> list[str]:
    """Generate symbol resolution candidates with India-first suffixes."""
    base = symbol.strip().upper()
    if not base:
        return []
    if base in _INDEX_ALIASES:
        return [_INDEX_ALIASES[base]]
    if "." in base:
        return [base]
    if base.startswith("^"):
        return [base]
    # India-first resolution: NSE, then BSE, while still allowing US symbols.
    return [f"{base}.NS", f"{base}.BO", base]


def _index_probe_candidates(symbol: str) -> list[str]:
    """Return ordered Yahoo probe symbols for one index, preferring empirically stable codes."""
    upper = symbol.strip().upper()
    if not upper:
        return []
    ordered = [
        _INDEX_PREFERRED_QUOTE_SYMBOLS.get(upper, upper),
        upper,
        *_INDEX_SYMBOL_FALLBACKS.get(upper, ()),
    ]
    seen: set[str] = set()
    out: list[str] = []
    for candidate in ordered:
        item = candidate.strip().upper()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _has_quote_data(info: dict[str, Any]) -> bool:
    """Return True when payload appears to contain usable quote fields."""
    if not info:
        return False
    keys = (
        "regularMarketPrice",
        "lastPrice",
        "regularMarketPreviousClose",
        "previousClose",
        "shortName",
        "longName",
        "currency",
    )
    return any(info.get(key) is not None for key in keys)


def _resolve_symbol(symbol: str) -> tuple[str, dict[str, Any] | None]:
    """Resolve user input to a concrete Yahoo symbol plus quote payload."""
    candidates = _candidate_symbols(symbol)
    if not candidates:
        return symbol, None

    for candidate in candidates:
        # Decision block: index quote probes prefer symbols with the strongest observed Yahoo coverage.
        to_try = _index_probe_candidates(candidate) if _is_known_index_symbol(candidate) else [candidate]
        for probe in to_try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                info = _get_quote_payload(probe)
            if _has_quote_data(info):
                return probe, info

    return candidates[0], None


def _search_symbol_options(query: str) -> list[dict[str, str]]:
    """Find top NSE symbol/name matches for fuzzy user input."""
    base = query.strip()
    if not base:
        return []
    options: list[dict[str, str]] = []
    q = base.upper().strip()
    q_compact = q.replace(" ", "")

    for row in _load_nse_universe():
        sym = row["symbol"]
        name = row["name"]
        sym_u = sym.upper()
        name_u = name.upper()
        name_compact = name_u.replace(" ", "")

        if q in sym_u or q in name_u or q_compact in sym_u or q_compact in name_compact:
            options.append(
                {
                    "symbol": f"{sym}.NS",
                    "name": name,
                    "exchange": "NSE",
                    "type": "EQUITY",
                }
            )

    def score(opt: dict[str, str]) -> int:
        sym = opt["symbol"].upper()
        name = opt["name"].upper()
        name_compact = name.replace(" ", "")
        value = 0
        if sym.startswith(f"{q}."):
            value += 200
        if sym.startswith(f"{q_compact}."):
            value += 180
        if q in sym:
            value += 120
        if q in name:
            value += 90
        if q_compact in name_compact:
            value += 80
        if name.startswith(q):
            value += 60
        return value

    options.sort(key=score, reverse=True)
    return options[:12]


def _load_nse_universe() -> list[dict[str, str]]:
    """Load and cache the local NSE symbol universe CSV."""
    global _NSE_UNIVERSE_CACHE
    if _NSE_UNIVERSE_CACHE is not None:
        return _NSE_UNIVERSE_CACHE
    if not _NSE_UNIVERSE_CSV.exists():
        _NSE_UNIVERSE_CACHE = []
        return _NSE_UNIVERSE_CACHE

    rows: list[dict[str, str]] = []
    try:
        with _NSE_UNIVERSE_CSV.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                symbol = str(row.get("SYMBOL", "")).strip()
                name = str(row.get("NAME OF COMPANY", "")).strip()
                if not symbol or not name:
                    continue
                rows.append({"symbol": symbol, "name": name})
    except OSError:
        _NSE_UNIVERSE_CACHE = []
        return _NSE_UNIVERSE_CACHE

    _NSE_UNIVERSE_CACHE = rows
    return _NSE_UNIVERSE_CACHE


def _choose_symbol_from_options(query: str, options: list[dict[str, str]]) -> str | None:
    """Interactively pick one symbol match, or return None when canceled."""
    if not options:
        return None
    if len(options) == 1:
        return options[0]["symbol"]
    if not sys.stdin.isatty():
        print(
            f"'{query}' is not a recognized symbol. Top matches: "
            + ", ".join(opt["symbol"] for opt in options[:5]),
            file=sys.stderr,
        )
        return None

    print(f"\n'{query}' is not an exact Yahoo ticker. Pick one:")
    for idx, opt in enumerate(options, start=1):
        print(f"{idx:>2}. {opt['symbol']:<16} {opt['name']} [{opt['exchange']} {opt['type']}]")
    print(" 0. Cancel")

    while True:
        choice = input("Enter number: ").strip()
        if choice == "0":
            return None
        if choice.isdigit():
            pos = int(choice)
            if 1 <= pos <= len(options):
                return options[pos - 1]["symbol"]
        print(f"Choose a number between 0 and {len(options)}.")


def _resolve_symbol_with_fallback(symbol: str) -> tuple[str, dict[str, Any] | None]:
    """Resolve symbols using Yahoo first, then local NSE fuzzy fallback."""
    resolved_symbol, info = _resolve_symbol(symbol)
    # Validation guardrail: keep index aliases in index space even when quote payload is sparse.
    # This prevents fuzzy equity suggestions for inputs like `defence` mapped to index symbols.
    if _index_alias_target(symbol) is not None:
        return resolved_symbol, info
    if info is not None:
        return resolved_symbol, info

    options = _search_symbol_options(symbol)
    chosen = _choose_symbol_from_options(symbol, options)
    if not chosen:
        return resolved_symbol, None

    chosen_symbol, chosen_info = _resolve_symbol(chosen)
    return chosen_symbol, chosen_info


def _print_code_matches(query: str) -> int:
    """Print top ticker-code matches for a free-text company query."""
    text = query.strip()
    if not text:
        print("Usage: code <company-or-symbol-query>", file=sys.stderr)
        return 2
    options = _search_symbol_options(text)
    if not options:
        print(f"No code matches found for '{text}'.", file=sys.stderr)
        return 2
    print(f"\nCode matches for '{text}':")
    print(f"{'Ticker':<18} {'Name':<48} {'Exch':<6}")
    for opt in options[:10]:
        print(f"{opt['symbol']:<18} {opt['name'][:48]:<48} {opt['exchange']:<6}")
    print()
    return 0


def _news_publish_timestamp(item: dict[str, Any]) -> dt.datetime | None:
    """Extract best-effort publish timestamp from one Yahoo news item."""
    for key in ("providerPublishTime", "published", "publishTime"):
        raw = item.get(key)
        if isinstance(raw, str):
            text = raw.strip()
            if text:
                try:
                    raw = float(text)
                except ValueError:
                    raw = None
        if isinstance(raw, (int, float)):
            try:
                epoch = float(raw)
                # Some providers send milliseconds; downshift to epoch-seconds.
                if epoch > 1e12:
                    epoch /= 1000.0
                if not math.isfinite(epoch):
                    continue
                return dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc)
            except (OverflowError, OSError, ValueError):
                continue

    for key in ("publishedAt", "pubDate", "displayTime"):
        raw = item.get(key)
        if isinstance(raw, str):
            text = raw.strip()
            if not text:
                continue
            try:
                # Normalize trailing `Z` to ISO offset so `fromisoformat` can parse.
                parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=dt.timezone.utc)
            except ValueError:
                continue
    return None


def _format_news_age(published_at: dt.datetime) -> str:
    """Format compact relative age text for one publish timestamp."""
    now_local = dt.datetime.now().astimezone()
    age = now_local - published_at.astimezone()
    seconds = int(age.total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def _news_wrap_width(default: int = 100) -> int:
    """Return a conservative wrap width for terminal-readable news output."""
    cols = shutil.get_terminal_size(fallback=(default, 24)).columns
    # Keep readability stable on very narrow terminals and avoid over-wide unreadable lines.
    return max(72, min(cols, 120))


def _wrap_news_block(text: str, initial_indent: str, subsequent_indent: str, width: int) -> str:
    """Wrap one news output line while preserving indentation intent."""
    return textwrap.fill(
        text,
        width=width,
        initial_indent=initial_indent,
        subsequent_indent=subsequent_indent,
        break_long_words=False,
        break_on_hyphens=False,
    )


def _print_symbol_news(symbol_input: str, limit: int = 5) -> int:
    """Resolve one symbol and print recent Yahoo Finance headlines."""
    token = symbol_input.strip()
    if not token:
        print("Usage: news <code>", file=sys.stderr)
        return 2

    resolved_symbol, info = _resolve_symbol_with_fallback(token)
    if info is None:
        print(f"Could not resolve symbol '{token}'.", file=sys.stderr)
        return 2

    _track_network_call("yfinance.Ticker")
    try:
        ticker = yf.Ticker(resolved_symbol)
    except Exception:
        ticker = None

    news_items: list[Any] = []
    if ticker is not None:
        try:
            prop_items = ticker.news
            if isinstance(prop_items, list):
                news_items = prop_items
        except Exception:
            news_items = []
        if not news_items:
            # Some yfinance builds expose news primarily through `get_news()`.
            get_news = getattr(ticker, "get_news", None)
            if callable(get_news):
                try:
                    fetched = get_news()
                    if isinstance(fetched, list):
                        news_items = fetched
                except Exception:
                    news_items = []

    if not isinstance(news_items, list) or not news_items:
        print(f"No Yahoo news found for '{resolved_symbol}'.", file=sys.stderr)
        return 2

    width = _news_wrap_width()
    entries: list[tuple[int, str, str, str, dt.datetime | None]] = []
    for original_idx, item in enumerate(news_items):
        if not isinstance(item, dict):
            continue
        # Yahoo payloads vary across yfinance versions (`item` vs nested `content` keys).
        payload = item
        content = item.get("content")
        if isinstance(content, dict):
            payload = content
        title = str(payload.get("title") or payload.get("headline") or "").strip()
        if not title:
            continue
        publisher = str(payload.get("publisher") or item.get("publisher") or "n/a").strip() or "n/a"

        # Prefer nested content timestamp, then outer wrapper as fallback.
        publish_dt = _news_publish_timestamp(payload)
        if publish_dt is None:
            publish_dt = _news_publish_timestamp(item)
        if publish_dt:
            local_dt = publish_dt.astimezone()
            published_txt = f"{local_dt.strftime('%d-%m-%y %H:%M')} ({_format_news_age(local_dt)})"
        else:
            published_txt = "n/a"

        link_val: Any = payload.get("link")
        if not link_val and isinstance(payload.get("canonicalUrl"), dict):
            link_val = payload["canonicalUrl"].get("url")
        link = str(link_val or "").strip()
        entries.append((original_idx, title, publisher, link, publish_dt))

    if not entries:
        print(f"No Yahoo news found for '{resolved_symbol}'.", file=sys.stderr)
        return 2

    # Keep timestamped items first and newest-first; preserve source order for ties/missing dates.
    entries.sort(
        key=lambda row: (
            0 if row[4] is not None else 1,
            -row[4].timestamp() if row[4] is not None else 0.0,
            row[0],
        )
    )

    top_n = max(1, limit)
    shown = entries[:top_n]
    print(f"\nNews: {resolved_symbol} (top {top_n})")
    for rendered, (_idx, title, _publisher, link, publish_dt) in enumerate(shown, start=1):
        if publish_dt:
            local_dt = publish_dt.astimezone()
            age_txt = _format_news_age(local_dt)
        else:
            age_txt = "time n/a"
        title_block = _wrap_news_block(title, initial_indent=f"* ({age_txt}) ", subsequent_indent="  ", width=width)
        print(_colorize(title_block, "cyan"))
        if link:
            link_block = _wrap_news_block(link, initial_indent="  ", subsequent_indent="  ", width=width)
            print(_colorize(link_block, "gray"))
        if rendered < len(shown):
            print()
    print()
    return 0


def _is_known_index_symbol(symbol: str) -> bool:
    """Return True when symbol matches configured/known index symbols or fallbacks."""
    upper = symbol.strip().upper()
    if not upper:
        return False
    if upper in _INDEX_NORMALIZATION_ALIASES:
        return True
    if upper in _INDEX_BOARD_SYMBOLS or upper in _INDEX_SYMBOL_FALLBACKS:
        return True
    return any(upper == fallback.upper() for fallbacks in _INDEX_SYMBOL_FALLBACKS.values() for fallback in fallbacks)


def _is_index_context_symbol(symbol: str | None) -> bool:
    """Return True when symbol should be treated as an index-mode context token."""
    if not symbol:
        return False
    token = symbol.strip()
    return token.startswith("^") or _is_known_index_symbol(token)


def _index_alias_target(symbol_input: str) -> str | None:
    """Resolve index-alias-like input to a target index symbol when applicable."""
    candidates = _candidate_symbols(symbol_input)
    if not candidates:
        return None
    candidate = candidates[0]
    return candidate if _is_known_index_symbol(candidate) else None


def _recent_direction_dots(symbol: str, days: int = 10) -> str | None:
    """Return colored up/down dots left-to-right from older to latest daily moves."""
    return quote_tools.recent_direction_dots(
        symbol=symbol,
        days=days,
        fetch_closes=_fetch_close_points_for_token,
        colorize=_colorize,
    )


def _return_horizon_summary(symbol: str) -> dict[str, float | None]:
    """Return 7D/1MO/3MO/6MO/9MO/1Y percent moves for quote output horizons."""
    return quote_tools.horizon_return_summary(
        symbol=symbol,
        fetch_closes=_fetch_close_points_for_token,
    )


def _signal_snapshot(symbol: str) -> dict[str, float | str | None]:
    """Return trend/momentum/risk diagnostics for quote output."""
    points, closes, _highs, _lows, volumes = _fetch_daily_ohlcv_for_period(symbol, "1y")
    return quote_tools.quote_signal_snapshot(points=points, closes=closes, volumes=volumes)


def _print_quote(input_symbol: str, resolved_symbol: str, include_after_hours: bool, preloaded_info: dict[str, Any] | None = None) -> int:
    """Render a compact quote snapshot with ranges and key ratios."""
    points, closes, _highs, _lows, volumes = _fetch_daily_ohlcv_for_period(resolved_symbol, "1y")
    trend_dots = quote_tools.recent_direction_dots_from_points(closes=closes, days=30, colorize=_colorize)
    return_summary = quote_tools.horizon_return_summary_from_points(points=points, closes=closes)
    signal_summary = quote_tools.quote_signal_snapshot(points=points, closes=closes, volumes=volumes)

    def _trend_dots_prefetched(_symbol: str, days: int) -> str | None:
        """Serve precomputed 30D dots to avoid duplicate history fetches."""
        return trend_dots

    def _return_summary_prefetched(_symbol: str) -> dict[str, float | None]:
        """Serve precomputed return horizons to avoid duplicate history fetches."""
        return return_summary

    def _signal_summary_prefetched(_symbol: str) -> dict[str, float | str | None]:
        """Serve precomputed signal snapshot to avoid duplicate history fetches."""
        return signal_summary

    quote_info = dict(preloaded_info) if preloaded_info is not None else None
    if quote_info is not None and _is_index_context_symbol(resolved_symbol):
        normalized = _normalize_snap_index_symbol(resolved_symbol)
        canonical_label = _index_label_for_symbol(normalized)
        if canonical_label:
            # Keep index naming consistent with board/catalog labels.
            quote_info["shortName"] = canonical_label

    return views.print_quote(
        input_symbol=input_symbol,
        resolved_symbol=resolved_symbol,
        include_after_hours=include_after_hours,
        preloaded_info=quote_info,
        get_quote_payload=_get_quote_payload,
        recent_direction_dots_fn=_trend_dots_prefetched,
        return_horizon_summary_fn=_return_summary_prefetched,
        signal_snapshot_fn=_signal_summary_prefetched,
        colorize=_colorize,
        fmt_price=_fmt_price,
        fmt_change=_fmt_change,
        fmt_compact_num=_fmt_compact_num,
        color_by_sign=_color_by_sign,
        range_line=_range_line,
    )


def _print_index_board() -> int:
    """Render a compact snapshot of selected India and global indices."""

    def _resolve_board_snapshots(rows: tuple[tuple[str, str], ...]) -> dict[str, tuple[str, dict[str, float | None]]]:
        """Resolve board rows via the shared grouped snapshot strategy."""
        primary_symbols = [symbol for symbol, _ in rows]
        candidate_map: dict[str, list[str]] = {
            symbol: _index_probe_candidates(symbol)
            for symbol in primary_symbols
        }
        # For index board, avoid quote-based day-range enrichment during candidate resolution.
        # Missing ranges are handled later via intraday fallback on displayed rows.
        chosen_snapshots, _passes_used = _resolve_group_candidate_snapshots(
            candidate_map,
            enrich_day_range_from_symbol_candidates_fn=lambda _symbols, _snapshot: None,
        )
        return chosen_snapshots

    all_rows = tuple([*_INDIA_INDEX_BOARD, *_GLOBAL_INDEX_BOARD])
    chosen_snapshots = _resolve_board_snapshots(all_rows)

    def _render_section(title: str, rows: tuple[tuple[str, str], ...]) -> None:
        """Render one section of the market board using resolved snapshots."""

        print(f"\n{title}")
        print(f"{'Index':<20} {'Ticker':<20} {'Price':>12} {'Change':>18} {'Range':>18}")
        rendered_rows: list[tuple[str, str, str, str, str, float | None, float | None]] = []
        for symbol, label in rows:
            chosen_symbol = symbol
            price = prev = day_low = day_high = None

            resolved = chosen_snapshots.get(symbol)
            if resolved is not None:
                chosen_symbol, snap = resolved
                price = snap.get("regularMarketPrice")
                prev = snap.get("regularMarketPreviousClose")
                day_low = snap.get("regularMarketDayLow")
                day_high = snap.get("regularMarketDayHigh")
                change_raw = snap.get("regularMarketChange")
                pct_raw = snap.get("regularMarketChangePercent")
            else:
                change_raw = None
                pct_raw = None

            change = None if price is None or prev is None else float(price) - float(prev)
            pct = None if change is None or not prev else (change / float(prev)) * 100
            # Some index symbols expose direct change/pct without previous-close anchors.
            if (change is None or pct is None) and change_raw is not None and pct_raw is not None:
                try:
                    change = float(change_raw)
                    pct = float(pct_raw)
                except (TypeError, ValueError):
                    pass
            if change is None or pct is None:
                # Guardrail: when batch daily snapshots provide only one close row,
                # fetch direct quote fields for change/pct before rendering n/a.
                quote_info = _get_quote_payload(chosen_symbol)
                try:
                    q_change = quote_info.get("regularMarketChange")
                    q_pct = quote_info.get("regularMarketChangePercent")
                    if q_change is not None and q_pct is not None:
                        change = float(q_change)
                        pct = float(q_pct)
                    elif price is not None and quote_info.get("regularMarketPreviousClose") is not None:
                        prev_q = float(quote_info.get("regularMarketPreviousClose"))
                        change = float(price) - prev_q
                        pct = (change / prev_q) * 100 if prev_q else None
                except (TypeError, ValueError):
                    pass
            price_txt = _fmt_price(price)
            if change is None or pct is None:
                change_txt = "n/a"
            else:
                # Color movement by sign for quick market breadth scan.
                change_txt = _colorize(_fmt_change(change, pct), _color_by_sign(change))
            try:
                low_f = float(day_low) if day_low is not None else None
                high_f = float(day_high) if day_high is not None else None
                price_f = float(price) if price is not None else None
            except (TypeError, ValueError):
                low_f = high_f = price_f = None
            if price_f is not None and (low_f is None or high_f is None or high_f <= low_f):
                # Some index quotes miss day range fields; derive from intraday candles.
                low_f, high_f = _fetch_day_range_fallback_candidates([chosen_symbol, symbol])
            if (
                price_f is not None
                and (low_f is None or high_f is None or high_f <= low_f)
                and prev is not None
            ):
                # Quote-only symbols sometimes expose dayLow/dayHigh equal to last price; use
                # a deterministic one-bar proxy from prev->last so range is still interpretable.
                prev_f = float(prev)
                if prev_f != price_f:
                    low_f = min(prev_f, price_f)
                    high_f = max(prev_f, price_f)
            if low_f is not None and high_f is not None and price_f is not None and high_f > low_f:
                range_txt = _colorize(_range_line(low_f, high_f, price_f, width=12), "cyan")
            else:
                range_txt = "n/a"

            pct_sort = float(pct) if pct is not None else None
            rendered_rows.append((label, chosen_symbol, price_txt, change_txt, range_txt, change, pct_sort))

        def _sort_key(row: tuple[str, str, str, str, str, float | None, float | None]) -> tuple[int, float]:
            """Sort rows as: green desc, red by smallest fall first, unknowns last."""
            _label, _chosen_symbol, _price_txt, _change_txt, _range_txt, change_val, pct_val = row
            if change_val is None or pct_val is None:
                return (2, 0.0)
            if change_val >= 0:
                return (0, -pct_val)
            return (1, abs(pct_val))

        # Keep output scan-friendly: all gainers first, then losers, then unknowns.
        for label, chosen_symbol, price_txt, change_txt, range_txt, _change, _pct in sorted(rendered_rows, key=_sort_key):
            # Keep NIFTY 50 visually prominent in sorted boards for quick scanning.
            if label == "NIFTY 50":
                label_txt = _colorize(label, "cyan")
                ticker_txt = _colorize(chosen_symbol, "cyan")
                price_cell_txt = _colorize(price_txt, "cyan")
            else:
                label_txt = label
                ticker_txt = chosen_symbol
                price_cell_txt = price_txt
            line = " ".join(
                [
                    _pad_cell(label_txt, 20, "left"),
                    _pad_cell(ticker_txt, 20, "left"),
                    _pad_cell(price_cell_txt, 12, "right"),
                    _pad_cell(change_txt, 18, "right"),
                    _pad_cell(range_txt, 18, "right"),
                ]
            )
            print(line)

    _render_section("India", _INDIA_INDEX_BOARD)
    _render_section("Global", _GLOBAL_INDEX_BOARD)
    print()
    return 0


def _print_index_catalog() -> int:
    """Print all curated index symbols that can be tracked in the board."""

    def _print_rows(title: str, rows: tuple[tuple[str, str], ...]) -> None:
        """Print one catalog section without live quote fetches."""
        print(f"\n{title}")
        print(f"{'Index':<24} {'Ticker':<20}")
        for symbol, label in rows:
            print(f"{label:<24} {symbol:<20}")

    print("\nIndex Catalog")
    print("=============")
    _print_rows("India", _INDIA_INDEX_BOARD)
    _print_rows("Global", _GLOBAL_INDEX_BOARD)
    print()
    return 0


def _normalize_snap_index_symbol(symbol: str) -> str:
    """Normalize an index symbol to the canonical key used by `snap` universes."""
    upper = symbol.strip().upper()
    if upper in _INDEX_NORMALIZATION_ALIASES:
        return _INDEX_NORMALIZATION_ALIASES[upper]
    if upper in _load_snap_universes():
        return upper
    # Resolve known index fallbacks to their canonical primary symbols.
    for canonical, fallbacks in _INDEX_SYMBOL_FALLBACKS.items():
        if upper == canonical or upper in (fallback.upper() for fallback in fallbacks):
            return canonical
    return upper


def _load_snap_universes() -> dict[str, tuple[str, tuple[str, ...]]]:
    """Load and cache snap constituent universes from the local CSV file."""
    global _SNAP_UNIVERSE_CACHE
    if _SNAP_UNIVERSE_CACHE is not None:
        return _SNAP_UNIVERSE_CACHE
    if not _INDEX_CONSTITUENTS_CSV.exists():
        _SNAP_UNIVERSE_CACHE = {}
        return _SNAP_UNIVERSE_CACHE

    grouped: dict[str, tuple[str, list[str]]] = {}
    try:
        with _INDEX_CONSTITUENTS_CSV.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                index_symbol = str(row.get("index_symbol", "")).strip().upper()
                index_label = str(row.get("index_label", "")).strip()
                constituent = str(row.get("constituent", "")).strip().upper()
                if not index_symbol or not index_label or not constituent:
                    continue
                if index_symbol not in grouped:
                    grouped[index_symbol] = (index_label, [])
                grouped[index_symbol][1].append(constituent)
    except OSError:
        _SNAP_UNIVERSE_CACHE = {}
        return _SNAP_UNIVERSE_CACHE

    _SNAP_UNIVERSE_CACHE = {key: (label, tuple(members)) for key, (label, members) in grouped.items()}
    return _SNAP_UNIVERSE_CACHE


def _snap_universe_for_symbol(symbol: str) -> tuple[str, tuple[str, ...]] | None:
    """Return the constituent universe configured for `snap` for a resolved index symbol."""
    normalized = _normalize_snap_index_symbol(symbol)
    return _load_snap_universes().get(normalized)


def _index_label_for_symbol(symbol: str) -> str:
    """Return display label for one index symbol from board config."""
    upper = symbol.strip().upper()
    for index_symbol, label in (*_INDIA_INDEX_BOARD, *_GLOBAL_INDEX_BOARD):
        if index_symbol.upper() == upper:
            return label
    return upper


def _index_quote_fallback_payload(symbol: str) -> dict[str, Any] | None:
    """Build a quote-like index payload from grouped snapshot fetch output."""
    upper = symbol.strip().upper()
    if not upper:
        return None
    candidates = _index_probe_candidates(upper)
    snapshots = _batch_index_snapshots(candidates)
    for candidate in candidates:
        snapshot = snapshots.get(candidate, {})
        if not isinstance(snapshot, dict):
            continue
        price = snapshot.get("regularMarketPrice")
        prev = snapshot.get("regularMarketPreviousClose")
        # Require at least one anchor value so quote rendering has meaningful content.
        if price is None and prev is None:
            continue
        return {
            "shortName": _index_label_for_symbol(upper),
            "currency": "n/a",
            "regularMarketPrice": price,
            "regularMarketPreviousClose": prev,
            "regularMarketDayLow": snapshot.get("regularMarketDayLow"),
            "regularMarketDayHigh": snapshot.get("regularMarketDayHigh"),
        }
    return None


def _expected_constituent_count(index_symbol: str) -> int | None:
    """Return expected constituent count when an index has a fixed known size."""
    return _INDEX_EXPECTED_CONSTITUENT_COUNTS.get(index_symbol.strip().upper())


def _print_index_constituent_snap(index_symbol: str) -> int:
    """Print a constituent price snapshot for the active supported index symbol."""
    normalized_index_symbol = _normalize_snap_index_symbol(index_symbol)
    universe = _snap_universe_for_symbol(index_symbol)
    if normalized_index_symbol not in _SNAP_ALLOWED_INDEX_SYMBOLS:
        print(
            "snap is available only for Indian indices (except INDIA VIX) and DOW JONES; "
            "switch to a supported index symbol from `index list` and retry.",
            file=sys.stderr,
        )
        return 3

    configured_universe = universe is not None
    if configured_universe:
        label, constituents = universe
    else:
        # Keep snap usable for any supported index even when constituent mapping is missing.
        label = _index_label_for_symbol(normalized_index_symbol)
        constituents = (normalized_index_symbol,)
        print(
            f"Constituent universe unavailable for {label}; showing index-only snapshot.",
            file=sys.stderr,
        )
    snapshots, passes_used = _fetch_group_snapshots_with_retries(list(constituents))

    expected = _expected_constituent_count(normalized_index_symbol) if configured_universe else None
    if not configured_universe:
        count_txt = "index-only"
    elif expected is not None and len(constituents) != expected:
        count_txt = f"{len(constituents)} configured / {expected} expected"
    else:
        count_txt = f"{len(constituents)} constituents"
    print(f"\nSnap: {label} ({count_txt})")
    if configured_universe and expected is not None and len(constituents) != expected:
        print(
            f"Warning: constituent list is incomplete for {label}; "
            f"showing configured subset from data/index_constituents.csv.",
            file=sys.stderr,
        )
    print(f"{'Symbol':<18} {'Price':>12} {'Change':>18} {'Range':>18}")
    rows: list[tuple[str, str, str, str, float | None, float | None]] = []
    for symbol in constituents:
        snapshot = snapshots.get(symbol, {})
        price = snapshot.get("regularMarketPrice")
        prev = snapshot.get("regularMarketPreviousClose")
        day_low = snapshot.get("regularMarketDayLow")
        day_high = snapshot.get("regularMarketDayHigh")
        change = None if price is None or prev is None else float(price) - float(prev)
        pct = None if change is None or not prev else (change / float(prev)) * 100
        price_txt = _fmt_price(price)
        if change is None or pct is None:
            change_txt = "n/a"
        else:
            change_txt = _colorize(_fmt_change(change, pct), _color_by_sign(change))
        try:
            low_f = float(day_low) if day_low is not None else None
            high_f = float(day_high) if day_high is not None else None
            price_f = float(price) if price is not None else None
        except (TypeError, ValueError):
            low_f = high_f = price_f = None
        if low_f is not None and high_f is not None and price_f is not None and high_f > low_f:
            range_txt = _colorize(_range_line(low_f, high_f, price_f, width=12), "cyan")
        else:
            range_txt = "n/a"

        pct_sort = float(pct) if pct is not None else None
        rows.append((symbol, price_txt, change_txt, range_txt, change, pct_sort))

    def _sort_key(row: tuple[str, str, str, str, float | None, float | None]) -> tuple[int, float]:
        """Sort rows as: green desc, red by smallest fall first, unknowns last."""
        _symbol, _price_txt, _change_txt, _range_txt, change_val, pct_val = row
        if change_val is None or pct_val is None:
            return (2, 0.0)
        if change_val >= 0:
            return (0, -pct_val)
        return (1, abs(pct_val))

    for symbol, price_txt, change_txt, range_txt, _change, _pct in sorted(rows, key=_sort_key):
        line = " ".join(
            [
                _pad_cell(symbol, 18, "left"),
                _pad_cell(price_txt, 12, "right"),
                _pad_cell(change_txt, 18, "right"),
                _pad_cell(range_txt, 18, "right"),
            ]
        )
        print(line)
    print(f"Snap fetch passes used: {passes_used}")
    print()
    return 0


def _fetch_day_range_fallback(symbol: str) -> tuple[float | None, float | None]:
    """Best-effort fallback to derive day low/high from intraday history."""
    return snapshot_service.fetch_day_range_fallback(symbol, yf.download, _track_network_call)


def _fetch_day_range_fallback_candidates(symbols: list[str]) -> tuple[float | None, float | None]:
    """Try intraday day-range derivation over ordered symbol candidates."""
    return snapshot_service.fetch_day_range_fallback_candidates(symbols, _fetch_day_range_fallback)


def _series_for_symbol_field(df: pd.DataFrame, symbol: str, field: str) -> pd.Series | None:
    """Extract one symbol+field series from yfinance batch output."""
    return snapshot_service.series_for_symbol_field(df, symbol, field)


def _has_usable_day_range(snapshot: dict[str, float | None]) -> bool:
    """Return True when a snapshot already has a valid day low/high pair."""
    return snapshot_service.has_usable_day_range(snapshot)


def _coerce_float(value: Any) -> float | None:
    """Convert a scalar-like value to float, returning None on parse failures."""
    return snapshot_service.coerce_float(value)


def _parse_day_range_text(value: Any) -> tuple[float | None, float | None]:
    """Parse textual day-range payloads like '31800.0 - 32100.5'."""
    return snapshot_service.parse_day_range_text(value)


def _extract_quote_day_range(info: dict[str, Any]) -> tuple[float | None, float | None]:
    """Extract day low/high from quote payload across known Yahoo key variants."""
    return snapshot_service.extract_quote_day_range(info)


def _enrich_snapshot_day_range_from_quote(symbol: str, snapshot: dict[str, float | None]) -> None:
    """Fill missing day low/high from quote payload when price exists."""
    if " " in symbol:
        return
    snapshot_service.enrich_snapshot_day_range_from_quote(symbol, snapshot, _get_quote_payload)


def _enrich_snapshot_day_range_from_symbol_candidates(
    symbols: list[str], snapshot: dict[str, float | None]
) -> None:
    """Try multiple symbol candidates to fill missing day low/high in one snapshot."""
    snapshot_service.enrich_snapshot_day_range_from_symbol_candidates(
        symbols,
        snapshot,
        _enrich_snapshot_day_range_from_quote,
    )


def _batch_index_snapshots(symbols: list[str]) -> dict[str, dict[str, float | None]]:
    """Fetch price/change/day-range snapshots for many symbols in batch."""
    return snapshot_service.batch_index_snapshots(symbols, yf.download, _track_network_call)


def _resolve_group_candidate_snapshots(
    candidate_map: dict[str, list[str]],
    enrich_day_range_from_symbol_candidates_fn: Callable[[list[str], dict[str, float | None]], None] | None = None,
) -> tuple[dict[str, tuple[str, dict[str, float | None]]], int]:
    """Resolve grouped snapshots with 3 batch passes, then direct per-symbol Ticker fallback."""
    enrich_fn = enrich_day_range_from_symbol_candidates_fn or _enrich_snapshot_day_range_from_symbol_candidates
    return snapshot_service.resolve_group_candidate_snapshots(
        candidate_map=candidate_map,
        batch_index_snapshots_fn=_batch_index_snapshots,
        get_quote_payload=_get_quote_payload,
        has_quote_data=_has_quote_data,
        ticker_fallback_pause=_ticker_fallback_pause,
        enrich_day_range_from_symbol_candidates_fn=enrich_fn,
        progress_scope=_progress_scope,
    )


def _fetch_group_snapshots_with_retries(symbols: list[str]) -> tuple[dict[str, dict[str, float | None]], int]:
    """Fetch grouped snapshots with 3 batch passes, then per-symbol fallback for unresolved symbols."""
    progress_scope = _progress_scope if len(symbols) > 1 else _silent_progress_scope
    return snapshot_service.fetch_group_snapshots_with_retries(
        symbols=symbols,
        batch_index_snapshots_fn=_batch_index_snapshots,
        get_quote_payload=_get_quote_payload,
        has_quote_data=_has_quote_data,
        ticker_fallback_pause=_ticker_fallback_pause,
        enrich_day_range_from_symbol_candidates_fn=_enrich_snapshot_day_range_from_symbol_candidates,
        progress_scope=progress_scope,
    )


def _fetch_close_points_for_token(symbol: str, period_token: str, interval: str) -> tuple[list[dt.datetime], list[float]]:
    """Download close-price points for a normalized period token and interval."""
    return price_history.fetch_close_points_for_token(
        symbol=symbol,
        period_token=period_token,
        interval=interval,
        download_fn=yf.download,
        track_network_call=_track_network_call,
    )


def _fetch_daily_ohlcv_for_period(
    symbol: str,
    period_token: str,
) -> tuple[list[dt.datetime], list[float], list[float | None], list[float | None], list[float | None]]:
    """Download one daily OHLCV payload for quote analytics."""
    return price_history.fetch_daily_ohlcv_for_period(
        symbol=symbol,
        period_token=period_token,
        download_fn=yf.download,
        track_network_call=_track_network_call,
    )


def _normalize_period_token(period_token: str) -> str | None:
    """Normalize user period token; accepts d/w/mo/y units and 'max'."""
    return timeframe.normalize_period_token(period_token)


def _period_token_days(period_token: str) -> int | None:
    """Approximate a normalized period token into calendar days."""
    return timeframe.period_token_days(period_token)


def _normalize_agg_token(token: str) -> str | None:
    """Normalize aggregation token to a yfinance interval string."""
    return timeframe.normalize_agg_token(token)


def _validate_period_interval(period_token: str, interval: str) -> str | None:
    """Validate period/interval compatibility and return an error message when invalid."""
    return timeframe.validate_period_interval(period_token, interval)


def _parse_swing_command_args(args: list[str], command_name: str) -> tuple[_ParsedSwingCommand | None, str | None]:
    """Parse `t`/`c` command arguments into a dataclass-driven command spec."""
    usage = (
        f"Usage: {command_name} | {command_name} <code> [period [agg]] | "
        f"{command_name} - <period> [agg] | {command_name} <code> - <period> [agg]"
    )
    if len(args) == 0:
        return _ParsedSwingCommand(), None

    # Dash form preserves benchmark context and only changes period/aggregation.
    if args[0] == "-":
        if len(args) not in {2, 3}:
            return None, f"Usage: {command_name} - <period> [agg]"
        period_token = _normalize_period_token(args[1])
        if period_token is None:
            return None, f"Unsupported period token '{args[1]}'."
        interval_override = None
        if len(args) == 3:
            interval_override = _normalize_agg_token(args[2])
            if interval_override is None:
                return None, f"Unsupported aggregation token '{args[2]}'."
        return _ParsedSwingCommand(period_token=period_token, interval_override=interval_override), None

    if len(args) >= 2 and args[1] == "-":
        if len(args) not in {3, 4}:
            return None, f"Usage: {command_name} <code> - <period> [agg]"
        period_token = _normalize_period_token(args[2])
        if period_token is None:
            return None, f"Unsupported period token '{args[2]}'."
        interval_override = None
        if len(args) == 4:
            interval_override = _normalize_agg_token(args[3])
            if interval_override is None:
                return None, f"Unsupported aggregation token '{args[3]}'."
        return _ParsedSwingCommand(
            period_token=period_token,
            interval_override=interval_override,
            benchmark_input=args[0],
        ), None

    if len(args) == 1:
        # Single token is ambiguous: treat as period if valid, else benchmark input.
        period_token = _normalize_period_token(args[0])
        if period_token is not None:
            return _ParsedSwingCommand(period_token=period_token), None
        return _ParsedSwingCommand(benchmark_input=args[0]), None

    if len(args) == 2:
        # Prefer `<period> <agg>` when both tokens match that shape.
        period_token = _normalize_period_token(args[0])
        interval_override = _normalize_agg_token(args[1])
        if period_token is not None and interval_override is not None:
            return _ParsedSwingCommand(period_token=period_token, interval_override=interval_override), None
        period_token = _normalize_period_token(args[1])
        if period_token is None:
            return None, usage
        return _ParsedSwingCommand(period_token=period_token, benchmark_input=args[0]), None

    if len(args) == 3:
        period_token = _normalize_period_token(args[1])
        interval_override = _normalize_agg_token(args[2])
        if period_token is None or interval_override is None:
            return None, f"Usage: {command_name} <code> <period> [agg]"
        return _ParsedSwingCommand(
            period_token=period_token,
            interval_override=interval_override,
            benchmark_input=args[0],
        ), None

    return None, usage


def _parse_intraday_command_args(args: list[str], command_name: str = "cc") -> tuple[_ParsedIntradayCommand | None, str | None]:
    """Parse intraday command arguments into a dataclass-driven command spec."""
    usage = (
        f"Usage: {command_name} | {command_name} <1m|5m|15m|30m|1hr> | "
        f"{command_name} <code> | {command_name} <code> <1m|5m|15m|30m|1hr>"
    )
    if len(args) == 0:
        return _ParsedIntradayCommand(), None
    if len(args) == 1:
        # Single token is either supported intraday interval (with aliases) or benchmark override.
        token = args[0].strip().lower()
        normalized_interval = _REPL_INTRADAY_INTERVAL_ALIASES.get(token)
        if normalized_interval is not None:
            return _ParsedIntradayCommand(interval=normalized_interval), None
        return _ParsedIntradayCommand(benchmark_input=args[0]), None
    if len(args) == 2:
        token = args[1].strip().lower()
        normalized_interval = _REPL_INTRADAY_INTERVAL_ALIASES.get(token)
        if normalized_interval is None:
            return None, usage
        return _ParsedIntradayCommand(interval=normalized_interval, benchmark_input=args[0]), None
    return None, usage


def _normalize_compare_period_token(period_token: str) -> str | None:
    """Normalize compare-period tokens, including month shorthand like `6m`."""
    normalized = _normalize_period_token(period_token)
    if normalized is not None:
        return normalized
    token = period_token.strip().lower()
    match = re.fullmatch(r"(\d+)m", token)
    if not match:
        return None
    return _normalize_period_token(f"{match.group(1)}mo")


def _parse_compare_command_args(args: list[str]) -> tuple[_ParsedCompareCommand | None, str | None]:
    """Parse `cmp` arguments as `<symbols...> [period [agg]]`."""
    usage = "Usage: cmp <symbol1> <symbol2> [symbolN ...] [period [agg]]"
    cleaned = [token.strip() for token in args if token.strip()]
    if len(cleaned) < 2:
        return None, usage
    if "--" in cleaned:
        return None, usage

    period_token = "6mo"
    interval_override = None
    symbols_end = len(cleaned)

    # Parse tail tokens from right to left so optional period/agg stay optional.
    maybe_interval = _normalize_agg_token(cleaned[-1])
    if maybe_interval is not None:
        interval_override = maybe_interval
        symbols_end -= 1
        if symbols_end < 3:
            return None, usage
        normalized_period = _normalize_compare_period_token(cleaned[symbols_end - 1])
        if normalized_period is None:
            return None, f"Unsupported period token '{cleaned[symbols_end - 1]}'."
        period_token = normalized_period
        symbols_end -= 1
    else:
        maybe_period = _normalize_compare_period_token(cleaned[-1])
        if maybe_period is not None and len(cleaned) >= 3:
            period_token = maybe_period
            symbols_end -= 1

    symbols_raw = cleaned[:symbols_end]
    deduped_symbols = tuple(dict.fromkeys(sym for sym in symbols_raw if sym))
    if len(deduped_symbols) < 2:
        return None, "Provide at least two distinct symbols for `cmp`."
    return _ParsedCompareCommand(symbols=deduped_symbols, period_token=period_token, interval_override=interval_override), None


def _resolve_benchmark_for_table(
    active_symbol: str,
    active_info: dict[str, Any] | None,
    benchmark_input: str | None,
) -> tuple[str | None, str | None, str | None]:
    """Resolve table benchmark symbol/label from optional user benchmark input."""
    if benchmark_input is None:
        benchmark_symbol, benchmark_label = _benchmark_symbol_for(active_symbol, active_info)
        return benchmark_symbol, benchmark_label, None
    bench_resolved, bench_info = _resolve_symbol_with_fallback(benchmark_input)
    if bench_info is None:
        return None, None, f"Could not resolve benchmark symbol '{benchmark_input}'."
    bench_label = str(bench_info.get("shortName") or bench_info.get("longName") or bench_resolved)
    return bench_resolved, bench_label, None


def _resolve_benchmark_override(benchmark_input: str | None) -> tuple[str | None, str | None]:
    """Resolve chart benchmark override input to a concrete symbol."""
    if benchmark_input is None:
        return None, None
    bench_resolved, bench_info = _resolve_symbol_with_fallback(benchmark_input)
    if bench_info is None:
        return None, f"Could not resolve benchmark symbol '{benchmark_input}'."
    return bench_resolved, None


def _benchmark_symbol_for(symbol: str, info: dict[str, Any] | None) -> tuple[str | None, str | None]:
    """Choose default benchmark: NIFTY 50 for India, NASDAQ otherwise."""
    upper_symbol = symbol.upper()
    country = str((info or {}).get("country") or "").upper()
    currency = str((info or {}).get("currency") or "").upper()
    exchange = str((info or {}).get("exchange") or "").upper()

    is_india = (
        upper_symbol.endswith(".NS")
        or upper_symbol.endswith(".BO")
        or country == "INDIA"
        or currency == "INR"
        or exchange in {"NSI", "NSE", "BSE"}
        or upper_symbol in {"^NSEI", "^NSEBANK", "^NSEFIN", "^BSESN"}
    )
    if is_india:
        if upper_symbol == "^NSEI":
            return None, None
        return "^NSEI", "NIFTY 50"

    if upper_symbol == "^IXIC":
        return None, None
    return "^IXIC", "NASDAQ"


def _market_profile_for(symbol: str, info: dict[str, Any] | None) -> tuple[ZoneInfo, int, int, int, int]:
    """Return market timezone and local open/close times for a symbol."""
    return market_hours.market_profile_for(symbol, info)


def _is_market_open_now(symbol: str, info: dict[str, Any] | None) -> bool:
    """Return True when the symbol's market is currently open."""
    return market_hours.is_market_open_now(symbol, info)


def _interval_minutes(interval: str) -> int | None:
    """Convert supported intraday interval token to minutes."""
    return market_hours.interval_minutes(interval)


def _extend_intraday_to_close(
    points: list[dt.datetime],
    prices: list[float],
    interval: str,
    symbol: str,
    info: dict[str, Any] | None,
) -> tuple[list[dt.datetime], list[float]]:
    """Extend intraday series to market close with NaN placeholders."""
    return market_hours.extend_intraday_to_close(points, prices, interval, symbol, info)


def _outperformance_pct(stock_value: float, bench_value: float) -> float:
    """Return outperformance in percent relative to benchmark value."""
    return timeframe.outperformance_pct(stock_value, bench_value)


def _downsample_series(dates: list[str], prices: list[float], max_points: int) -> tuple[list[str], list[float]]:
    """Downsample paired date/price arrays to a display-friendly size."""
    return views.downsample_series(dates, prices, max_points)


def _checkpoint_indices(length: int, points: int = 6) -> list[int]:
    """Return evenly spaced checkpoint indices for tabular summaries."""
    return timeframe.checkpoint_indices(length, points=points)


def _print_rebased_table_output(
    symbol: str,
    benchmark_label: str,
    period_token: str,
    interval: str,
    dates: list[str],
    stock_values: list[float],
    bench_values: list[float],
) -> None:
    """Print a normalized rebased stock-vs-benchmark table block."""
    views.print_rebased_table_output(
        symbol=symbol,
        benchmark_label=benchmark_label,
        period_token=period_token,
        interval=interval,
        dates=dates,
        stock_values=stock_values,
        bench_values=bench_values,
        colorize=_colorize,
        color_by_sign=_color_by_sign,
        checkpoint_indices_fn=_checkpoint_indices,
    )


def _build_rebased_frame(
    stock_points: list[dt.datetime],
    stock_prices: list[float],
    bench_points: list[dt.datetime],
    bench_prices: list[float],
    tz: ZoneInfo,
    intraday: bool,
) -> pd.DataFrame | None:
    """Build aligned stock/benchmark frame with rebased metrics using pandas."""
    return views.build_rebased_frame(
        stock_points=stock_points,
        stock_prices=stock_prices,
        bench_points=bench_points,
        bench_prices=bench_prices,
        tz=tz,
        intraday=intraday,
    )


def _build_multi_rebased_frame(
    series_by_symbol: list[tuple[str, list[dt.datetime], list[float]]],
    tz: ZoneInfo,
    intraday: bool,
) -> pd.DataFrame | None:
    """Align and rebase many symbol series to a shared base=100 frame."""
    return views.build_multi_rebased_frame(
        series_by_symbol=series_by_symbol,
        tz=tz,
        intraday=intraday,
    )


def _print_compare_table_output(
    resolved_symbols: list[str],
    period_token: str,
    interval: str,
    frame: pd.DataFrame,
) -> None:
    """Print multi-instrument rebased table without delta/alpha columns."""
    views.print_compare_table_output(
        resolved_symbols=resolved_symbols,
        period_token=period_token,
        interval=interval,
        frame=frame,
        colorize=_colorize,
        color_by_sign=_color_by_sign,
        checkpoint_indices_fn=_checkpoint_indices,
    )


def _render_compare_table(symbol_inputs: list[str], period_token: str, interval_override: str | None = None) -> int:
    """Resolve many symbols and render a shared rebased compare table."""
    interval = interval_override or _table_interval_for_period_token(period_token)
    interval_error = _validate_period_interval(period_token, interval)
    if interval_error:
        print(interval_error, file=sys.stderr)
        return 3

    resolved_symbols: list[str] = []
    series_by_symbol: list[tuple[str, list[dt.datetime], list[float]]] = []
    for token in symbol_inputs:
        resolved, info = _resolve_symbol_with_fallback(token)
        if info is None:
            print(f"Could not resolve symbol '{token}'.", file=sys.stderr)
            return 3
        points, prices = _fetch_close_points_for_token(resolved, period_token=period_token, interval=interval)
        if not prices:
            print(
                f"No historical data for '{resolved}' with period={period_token} interval={interval}.",
                file=sys.stderr,
            )
            return 3
        resolved_symbols.append(resolved)
        series_by_symbol.append((resolved, points, prices))

    tz = _market_profile_for(resolved_symbols[0], None)[0]
    intraday = interval in _INTRADAY_INTERVALS
    frame = _build_multi_rebased_frame(series_by_symbol=series_by_symbol, tz=tz, intraday=intraday)
    if frame is None:
        print("No overlapping dates between compare symbols.", file=sys.stderr)
        return 3

    _print_compare_table_output(
        resolved_symbols=resolved_symbols,
        period_token=period_token,
        interval=interval,
        frame=frame,
    )
    return 0


def _draw_chart(
    symbol: str,
    period: str,
    interval: str,
    height: int,
    width: int,
    info: dict[str, Any] | None = None,
    benchmark_override: str | None = None,
) -> int:
    """Render the main coaxial chart plus rebased benchmark summary table."""
    interval_error = _validate_period_interval(period, interval)
    if interval_error:
        print(interval_error, file=sys.stderr)
        return 3

    points, prices = _fetch_close_points_for_token(symbol, period_token=period, interval=interval)
    if not prices:
        print(
            f"No historical data for '{symbol}' with period={period} interval={interval}.",
            file=sys.stderr,
        )
        return 3

    core_points = list(points)
    core_prices = list(prices)

    intraday = interval in _INTRADAY_INTERVALS
    if intraday:
        # Keep x-axis running to market close for active intraday sessions.
        points, prices = _extend_intraday_to_close(points, prices, interval=interval, symbol=symbol, info=info)
    tz = _market_profile_for(symbol, info)[0]
    dates = [
        p.astimezone(tz).strftime("%H:%M") if intraday else p.strftime("%d-%m-%y")
        for p in points
    ]
    core_dates = [
        p.astimezone(tz).strftime("%H:%M") if intraday else p.strftime("%d-%m-%y")
        for p in core_points
    ]

    color = "green" if core_prices[-1] >= core_prices[0] else "red"
    last_price = core_prices[-1]
    first_price = core_prices[0]
    low = min(core_prices)
    high = max(core_prices)
    delta = last_price - first_price
    delta_pct = (delta / first_price) * 100 if first_price else 0.0
    if benchmark_override:
        benchmark_symbol = benchmark_override
        benchmark_info = _get_quote_payload(benchmark_symbol)
        benchmark_label = str(benchmark_info.get("shortName") or benchmark_info.get("longName") or benchmark_symbol)
    else:
        benchmark_symbol, benchmark_label = _benchmark_symbol_for(symbol, info)
    benchmark_dates: list[str] = []
    benchmark_prices: list[float] = []

    if benchmark_symbol:
        b_points, b_prices = _fetch_close_points_for_token(benchmark_symbol, period_token=period, interval=interval)
        if b_points:
            frame = _build_rebased_frame(
                stock_points=points,
                stock_prices=prices,
                bench_points=b_points,
                bench_prices=b_prices,
                tz=tz,
                intraday=intraday,
            )
            if frame is not None:
                benchmark_dates = frame["date"].astype(str).tolist()
                benchmark_prices = frame["bench_on_stock_axis"].astype(float).tolist()
    title = f"{symbol.upper()} close ({period}, {interval})  {_fmt_change(delta, delta_pct)}"
    plt.clear_data()
    plt.clear_figure()
    plt.theme("pro")
    plt.plotsize(width, height)
    plt.title(title)
    plt.xlabel("Date")
    plt.ylabel("Price")
    plt.frame(True)
    plt.yfrequency(8)
    plot_dates, plot_prices = _downsample_series(dates, prices, max_points=max(30, width - 12))
    if intraday:
        # Plot intraday on numeric x to support custom session tick labels.
        x_vals = list(range(len(plot_prices)))
        plt.plot(x_vals, plot_prices, color=color, marker="hd")
        if benchmark_dates and benchmark_prices and benchmark_label:
            plot_b_dates, plot_b_prices = _downsample_series(
                benchmark_dates,
                benchmark_prices,
                max_points=max(30, width - 12),
            )
            date_pos: dict[str, int] = {d: i for i, d in enumerate(plot_dates)}
            b_x = [date_pos[d] for d in plot_b_dates if d in date_pos]
            b_y = [v for d, v in zip(plot_b_dates, plot_b_prices) if d in date_pos]
            if b_x:
                plt.plot(b_x, b_y, color="yellow", marker="dot")
                plt.scatter([b_x[-1]], [b_y[-1]], color="white", marker="dot")
        try:
            last_pos = plot_dates.index(core_dates[-1])
        except ValueError:
            last_pos = len(plot_dates) - 1
        plt.scatter([last_pos], [core_prices[-1]], color="cyan", marker="dot")
        xt_pos = sorted({0, len(plot_dates) // 2, len(plot_dates) - 1})
        xt_lbl = [plot_dates[i] for i in xt_pos]
        plt.xticks(xt_pos, xt_lbl)
    else:
        plt.date_form("d-m-y")
        plt.xfrequency(max(4, min(10, len(dates) // 12 or 4)))
        plt.plot(plot_dates, plot_prices, color=color, marker="hd")
        if benchmark_dates and benchmark_prices and benchmark_label:
            plot_b_dates, plot_b_prices = _downsample_series(
                benchmark_dates,
                benchmark_prices,
                max_points=max(30, width - 12),
            )
            plt.plot(plot_b_dates, plot_b_prices, color="yellow", marker="dot")
            plt.scatter([plot_b_dates[-1]], [plot_b_prices[-1]], color="white", marker="dot")
        plt.scatter([core_dates[-1]], [core_prices[-1]], color="cyan", marker="dot")
    plt.grid(True, False)
    plt.show()

    range_bar = _range_line(low, high, last_price, width=max(24, min(50, width // 2)))
    range_bar = _colorize(range_bar, "cyan")
    move_txt = _colorize(_fmt_change(delta, delta_pct), _color_by_sign(delta))
    print(f"Day Range  {range_bar}  {low:,.2f} .. {high:,.2f}")
    wk52_low = wk52_high = None
    if isinstance(info, dict):
        # Reuse quote payload fields when available; avoid extra fetches for 52W context.
        wk52_low = info.get("fiftyTwoWeekLow")
        wk52_high = info.get("fiftyTwoWeekHigh")
        if wk52_low is None:
            wk52_low = info.get("yearLow")
        if wk52_high is None:
            wk52_high = info.get("yearHigh")
    try:
        wk52_low_f = float(wk52_low) if wk52_low is not None else None
        wk52_high_f = float(wk52_high) if wk52_high is not None else None
    except (TypeError, ValueError):
        wk52_low_f = wk52_high_f = None
    if wk52_low_f is not None and wk52_high_f is not None and wk52_high_f > wk52_low_f:
        wk52_bar = _colorize(_range_line(wk52_low_f, wk52_high_f, last_price, width=max(24, min(50, width // 2))), "yellow")
        print(f"52W Range  {wk52_bar}  {wk52_low_f:,.2f} .. {wk52_high_f:,.2f}")
    print(f"Move: {move_txt} | From: {core_dates[0]} -> {core_dates[-1]}")
    if benchmark_dates and benchmark_prices and benchmark_label:
        print(f"Benchmark: {benchmark_label} ({benchmark_symbol}) rebased to start value")
    return 0


def _table_interval_for_period_token(period_token: str) -> str:
    """Pick default table aggregation interval from period token length."""
    return timeframe.table_interval_for_period_token(period_token)


def _interval_for_chart_period(period_token: str) -> str:
    """Pick default chart interval from period token length."""
    return timeframe.interval_for_chart_period(period_token)


def _render_rebased_table(
    symbol: str,
    info: dict[str, Any] | None,
    benchmark_symbol: str | None,
    benchmark_label: str | None,
    period_token: str,
    interval_override: str | None = None,
) -> int:
    """Render rebased stock-vs-benchmark table for a given period."""
    # Table defaults are intentionally coarser to prioritize readability.
    interval = interval_override or _table_interval_for_period_token(period_token)
    interval_error = _validate_period_interval(period_token, interval)
    if interval_error:
        print(interval_error, file=sys.stderr)
        return 3
    s_points, s_prices = _fetch_close_points_for_token(symbol, period_token=period_token, interval=interval)
    if not s_prices:
        print(f"No historical data for '{symbol}' with period={period_token} interval={interval}.", file=sys.stderr)
        return 3
    if not benchmark_symbol or not benchmark_label:
        print("No benchmark available for this symbol.", file=sys.stderr)
        return 3

    b_points, b_prices = _fetch_close_points_for_token(benchmark_symbol, period_token=period_token, interval=interval)
    if not b_prices:
        print(
            f"No historical data for benchmark '{benchmark_symbol}' with period={period_token} interval={interval}.",
            file=sys.stderr,
        )
        return 3

    # Rebase only on shared timestamps to avoid misleading relative math.
    frame = _build_rebased_frame(
        stock_points=s_points,
        stock_prices=s_prices,
        bench_points=b_points,
        bench_prices=b_prices,
        tz=_market_profile_for(symbol, info)[0],
        intraday=interval in _INTRADAY_INTERVALS,
    )
    if frame is None or frame.empty:
        print("No overlapping dates between stock and benchmark.", file=sys.stderr)
        return 3

    overlap_dates = frame["date"].astype(str).tolist()
    overlap_stock = frame["stock"].astype(float).tolist()
    overlap_bench = frame["bench"].astype(float).tolist()

    _print_rebased_table_output(
        symbol=symbol,
        benchmark_label=benchmark_label,
        period_token=period_token,
        interval=interval,
        dates=overlap_dates,
        stock_values=overlap_stock,
        bench_values=overlap_bench,
    )
    return 0


def _prompt_for_symbol(symbol: str | None) -> str:
    """Build the REPL prompt string from the active symbol."""
    if symbol:
        label = symbol.upper()
        if label.startswith("^"):
            label = label[1:]
        if "." in label:
            label = label.split(".", 1)[0]
        return f"tickertrail>{label.lower()}> "
    return "tickertrail> "


def _prompt_for_context(symbol: str | None, watchlist_name: str | None) -> str:
    """Build REPL prompt from active watchlist context or active symbol."""
    if watchlist_name:
        return f"{watchlist_name}> "
    return _prompt_for_symbol(symbol)


def _print_watchlist_snapshot(watchlist_name: str) -> int:
    """Render a live snapshot board for one stored watchlist."""
    symbols = _watchlist_symbols(watchlist_name)
    if symbols is None:
        print(f"Watchlist '{watchlist_name}' not found.", file=sys.stderr)
        return 3
    if not symbols:
        print(f"Watchlist '{watchlist_name}' is empty. Use `add <code>` in this mode.", file=sys.stderr)
        return 3

    benchmark_symbol = "^NSEI"
    fetch_symbols = list(dict.fromkeys([*symbols, benchmark_symbol]))
    snapshots, passes_used = _fetch_group_snapshots_with_retries(fetch_symbols)
    print()
    print(f"{'Symbol':<16} {'Price':>12} {'Change':>18} {'Range':>18}")
    rows: list[tuple[str, str, str, float | None, float | None, str]] = []
    for symbol in symbols:
        snapshot = snapshots.get(symbol, {})
        price = snapshot.get("regularMarketPrice")
        prev = snapshot.get("regularMarketPreviousClose")
        day_low = snapshot.get("regularMarketDayLow")
        day_high = snapshot.get("regularMarketDayHigh")
        change = None if price is None or prev is None else float(price) - float(prev)
        pct = None if change is None or not prev else (change / float(prev)) * 100
        if change is None or pct is None:
            change_txt = "n/a"
        else:
            change_txt = _colorize(_fmt_change(change, pct), _color_by_sign(change))
        range_txt = "n/a"
        try:
            low_f = float(day_low) if day_low is not None else None
            high_f = float(day_high) if day_high is not None else None
            price_f = float(price) if price is not None else None
            if low_f is not None and high_f is not None and price_f is not None and high_f > low_f:
                range_txt = _range_line(low_f, high_f, price_f, width=16)
        except (TypeError, ValueError):
            range_txt = "n/a"

        pct_sort = float(pct) if pct is not None else None
        rows.append((symbol, _fmt_price(price), change_txt, change, pct_sort, range_txt))

    def _sort_key(row: tuple[str, str, str, float | None, float | None, str]) -> tuple[int, float]:
        """Sort rows as: green desc, red by smallest fall first, unknowns last."""
        _symbol, _price_txt, _change_txt, change_val, pct_val, _range_txt = row
        if change_val is None or pct_val is None:
            return (2, 0.0)
        if change_val >= 0:
            return (0, -pct_val)
        return (1, abs(pct_val))

    eq_weight_pcts: list[float] = []
    for symbol, price_txt, change_txt, _change, pct_val, range_txt in sorted(rows, key=_sort_key):
        line = " ".join(
            [
                _pad_cell(symbol, 16, "left"),
                _pad_cell(price_txt, 12, "right"),
                _pad_cell(change_txt, 18, "right"),
                _pad_cell(range_txt, 18, "right"),
            ]
        )
        print(line)
        if pct_val is not None:
            eq_weight_pcts.append(float(pct_val))
    if eq_weight_pcts:
        eq_pct = sum(eq_weight_pcts) / float(len(eq_weight_pcts))
        eq_txt = _colorize(f"{eq_pct:+.2f}%", _color_by_sign(eq_pct))
        print(f"Equal-Weight 1D  {eq_txt}")
        benchmark_snapshot = snapshots.get(benchmark_symbol, {})
        bench_price = benchmark_snapshot.get("regularMarketPrice")
        bench_prev = benchmark_snapshot.get("regularMarketPreviousClose")
        try:
            bench_pct = None if bench_price is None or bench_prev in (None, 0) else ((float(bench_price) / float(bench_prev)) - 1.0) * 100.0
        except (TypeError, ValueError, ZeroDivisionError):
            bench_pct = None
        if bench_pct is not None:
            bench_txt = _colorize(f"{bench_pct:+.2f}%", _color_by_sign(bench_pct))
            alpha = eq_pct - bench_pct
            alpha_txt = _colorize(f"{alpha:+.2f}%", _color_by_sign(alpha))
            print(f"NIFTY 50 1D     {bench_txt}")
            print(f"Alpha           {alpha_txt}")
        else:
            print("NIFTY 50 1D     n/a")
            print("Alpha           n/a")
    else:
        print("Equal-Weight 1D  n/a")
    print(f"Watchlist snap fetch passes used: {passes_used}")
    return 0


def _parse_moves_period(args: list[str]) -> tuple[str | None, str | None]:
    """Parse `moves` period argument and enforce supported horizons."""
    if len(args) > 1:
        return None, f"Usage: moves [{_ANALYTICS_PERIOD_HINT}]"
    if not args:
        return "1mo", None

    token = _normalize_period_token(args[0])
    if not _is_analytics_period_token(token):
        return None, f"Usage: moves [{_ANALYTICS_PERIOD_HINT}]"
    return token, None


def _parse_scope_override_with_period(
    args: list[str],
    *,
    command_name: str,
    period_tokens: set[str] | None = None,
    default_period: str,
    period_validator: Callable[[str | None], bool] | None = None,
    period_hint: str | None = None,
) -> tuple[list[str] | None, str | None, str | None]:
    """Parse optional `on <codes...> [period]` grammar for analytics commands."""
    if period_validator is None:
        token_set = period_tokens or set()
        period_validator = lambda token: token in token_set if token is not None else False
    if period_hint is None:
        if period_tokens:
            period_hint = "|".join(sorted(period_tokens, key=lambda token: (_period_token_days(token) or 0, token)))
        else:
            period_hint = "period"
    usage = f"Usage: {command_name} [{period_hint}] | {command_name} on <code1> <code2> ... [{period_hint}]"
    cleaned = [token.strip() for token in args if token.strip()]
    if not cleaned:
        return None, default_period, None

    if cleaned[0].lower() != "on":
        if len(cleaned) != 1:
            return None, None, usage
        token = _normalize_period_token(cleaned[0])
        if not period_validator(token):
            return None, None, usage
        return None, token, None

    if len(cleaned) < 2:
        return None, None, usage

    # Decision block: when `on` is present, parse symbols first and treat a valid trailing
    # period token as optional override. Any invalid trailing period-like token is rejected.
    symbol_inputs = cleaned[1:]
    period_token = default_period
    if len(symbol_inputs) > 1:
        maybe_period = _normalize_period_token(symbol_inputs[-1])
        if period_validator(maybe_period):
            period_token = maybe_period
            symbol_inputs = symbol_inputs[:-1]
        elif maybe_period is not None:
            return None, None, usage
    if not symbol_inputs:
        return None, None, usage
    return symbol_inputs, period_token, None


def _parse_scope_override_no_period(
    args: list[str],
    *,
    command_name: str,
) -> tuple[list[str] | None, str | None]:
    """Parse optional `on <codes...>` grammar for no-period analytics commands."""
    usage = f"Usage: {command_name} | {command_name} on <code1> <code2> ..."
    cleaned = [token.strip() for token in args if token.strip()]
    if not cleaned:
        return None, None
    if cleaned[0].lower() != "on" or len(cleaned) < 2:
        return None, usage
    return cleaned[1:], None


def _is_analytics_period_token(token: str | None) -> bool:
    """Return True for analytics-board period tokens (`Nd`, `Nmo<12`, `Ny`)."""
    if token is None:
        return False
    match = re.fullmatch(r"(\d+)(d|mo|y)", token)
    if not match:
        return False
    count = int(match.group(1))
    unit = match.group(2)
    if count <= 0:
        return False
    if unit == "mo":
        return count < 12
    return True


def _parse_relret_args(args: list[str]) -> tuple[list[str] | None, str | None, str | None, str | None]:
    """Parse `relret` grammar with optional explicit symbols and benchmark override.

    Supported forms:
    - `relret [period] [vs <benchmark>]`
    - `relret [period] vs <benchmark> [period]`
    - `relret on <code1> <code2> ... [period] [vs <benchmark> [period]]`
    """
    usage = (
        f"Usage: relret [{_ANALYTICS_PERIOD_HINT}] [vs <benchmark>] | "
        f"relret on <code1> <code2> ... [{_ANALYTICS_PERIOD_HINT}] [vs <benchmark>]"
    )
    cleaned = [token.strip() for token in args if token.strip()]
    if not cleaned:
        return None, "1mo", None, None

    benchmark_input: str | None = None
    period_after_vs: str | None = None
    head_tokens = cleaned
    if "vs" in (token.lower() for token in cleaned):
        # Decision block: keep `vs` syntax explicit and deterministic with one benchmark token,
        # with optional trailing period token after benchmark.
        vs_positions = [idx for idx, token in enumerate(cleaned) if token.lower() == "vs"]
        if len(vs_positions) != 1:
            return None, None, None, usage
        vs_idx = vs_positions[0]
        tail = cleaned[vs_idx + 1 :]
        if len(tail) not in {1, 2}:
            return None, None, None, usage
        benchmark_input = tail[0]
        if benchmark_input.lower() == "vs":
            return None, None, None, usage
        if len(tail) == 2:
            maybe_period = _normalize_period_token(tail[1])
            if not _is_analytics_period_token(maybe_period):
                return None, None, None, usage
            period_after_vs = maybe_period
        head_tokens = cleaned[:vs_idx]

    if not head_tokens:
        if period_after_vs is None:
            # relret vs <benchmark>
            return None, "1mo", benchmark_input, None
        # relret vs <benchmark> <period>
        return None, period_after_vs, benchmark_input, None

    if head_tokens[0].lower() == "on":
        if len(head_tokens) < 2:
            return None, None, None, usage
        symbol_tokens = head_tokens[1:]
        period_token = period_after_vs or "1mo"
        if len(symbol_tokens) > 1:
            maybe_period = _normalize_period_token(symbol_tokens[-1])
            if _is_analytics_period_token(maybe_period):
                if period_after_vs is not None:
                    return None, None, None, usage
                period_token = maybe_period
                symbol_tokens = symbol_tokens[:-1]
            elif maybe_period is not None:
                return None, None, None, usage
        if not symbol_tokens:
            return None, None, None, usage
        return symbol_tokens, period_token, benchmark_input, None

    if len(head_tokens) > 1:
        return None, None, None, usage
    token = _normalize_period_token(head_tokens[0])
    if not _is_analytics_period_token(token):
        return None, None, None, usage
    if period_after_vs is not None:
        return None, None, None, usage
    return None, token, benchmark_input, None


def _parse_corr_period(args: list[str]) -> tuple[str | None, str | None]:
    """Parse `corr` period argument and enforce supported horizons."""
    if len(args) > 1:
        return None, f"Usage: corr [{_ANALYTICS_PERIOD_HINT}]"
    if not args:
        return "1mo", None

    token = _normalize_period_token(args[0])
    if not _is_analytics_period_token(token):
        return None, f"Usage: corr [{_ANALYTICS_PERIOD_HINT}]"
    return token, None


def _moves_days_for_period(period_token: str) -> int:
    """Return calendar days to render move dots for one supported period token."""
    return _MOVES_DAYS_BY_PERIOD.get(period_token, 30)


def _period_return_from_closes(closes: list[float]) -> float | None:
    """Return period percent move from first to last close."""
    if len(closes) < 2:
        return None
    first = float(closes[0])
    last = float(closes[-1])
    if first == 0:
        return None
    return ((last / first) - 1.0) * 100.0


def _close_series_for_period(symbol: str, period_token: str) -> tuple[list[dt.datetime], list[float]]:
    """Fetch one daily close series for period-level analytics commands."""
    points, closes = _fetch_close_points_for_token(symbol, period_token=period_token, interval="1d")
    return points, closes


def _relret_benchmark_for_context(current_symbol: str | None, active_watchlist: str | None) -> tuple[str | None, str]:
    """Resolve benchmark symbol/label for relret command in current context."""
    if active_watchlist:
        return "^NSEI", "NIFTY 50"
    if current_symbol and (_is_known_index_symbol(current_symbol) or current_symbol.strip().startswith("^")):
        # Canonicalize index fallbacks (for example NIFTY_NEXT_50.NS -> ^NIFTYNXT50)
        # so history fetches use the strongest Yahoo symbol.
        canonical_symbol = _normalize_snap_index_symbol(current_symbol)
        return canonical_symbol, _index_label_for_symbol(canonical_symbol)
    if current_symbol:
        benchmark_symbol, benchmark_label = _benchmark_symbol_for(current_symbol, None)
        if benchmark_symbol and benchmark_label:
            return benchmark_symbol, benchmark_label
    return None, "n/a"


def _print_relret_snapshot(
    current_symbol: str | None,
    active_watchlist: str | None,
    period_token: str,
    explicit_symbols: list[str] | None = None,
    benchmark_input: str | None = None,
) -> int:
    """Print relative-return ranking for watchlist/index context or explicit symbol basket."""
    if explicit_symbols is not None:
        symbols = _resolve_analytics_symbol_inputs(explicit_symbols)
        if symbols is None:
            return 3
        title = "Explicit symbols"
        # Decision block: explicit baskets should be context-agnostic and deterministic.
        benchmark_symbol, benchmark_label = "^NSEI", "NIFTY 50"
    else:
        title, symbols = _moves_targets_for_context(current_symbol=current_symbol, active_watchlist=active_watchlist)
        if title is None or symbols is None:
            return 3
        benchmark_symbol, benchmark_label = _relret_benchmark_for_context(
            current_symbol=current_symbol,
            active_watchlist=active_watchlist,
        )

    if benchmark_input is not None:
        benchmark_symbol_resolved, benchmark_info = _resolve_symbol_with_fallback(benchmark_input)
        if benchmark_info is None:
            print(f"Could not resolve benchmark symbol '{benchmark_input}'.", file=sys.stderr)
            return 3
        benchmark_symbol = benchmark_symbol_resolved
        benchmark_label = str(benchmark_info.get("shortName") or benchmark_info.get("longName") or benchmark_symbol_resolved)

    if benchmark_symbol is None:
        print("No benchmark available for relret in this context.", file=sys.stderr)
        return 3

    _bench_points, bench_closes = _close_series_for_period(benchmark_symbol, period_token=period_token)
    bench_ret = _period_return_from_closes(bench_closes)
    if bench_ret is None:
        print(f"No historical data for benchmark '{benchmark_symbol}' with period={period_token}.", file=sys.stderr)
        return 3

    label = period_token.upper()
    print()
    print(f"Relative Return ({label}) - {title} vs {benchmark_label} ({benchmark_symbol})")
    print(f"{'Symbol':<16} {'Return':>10} {'Bench':>10} {'RelRet':>10}")

    rows: list[tuple[str, str, str, str, float | None, int]] = []
    # Track valid stock returns so watchlist mode can print equal-weight summary vs benchmark.
    valid_returns: list[float] = []
    for idx, symbol in enumerate(symbols):
        _points, closes = _close_series_for_period(symbol, period_token=period_token)
        ret = _period_return_from_closes(closes)
        if ret is None:
            rows.append((symbol, "n/a", f"{bench_ret:+.2f}%", "n/a", None, idx))
            continue
        valid_returns.append(ret)
        relret = ret - bench_ret
        rows.append(
            (
                symbol,
                _colorize(f"{ret:+.2f}%", _color_by_sign(ret)),
                _colorize(f"{bench_ret:+.2f}%", _color_by_sign(bench_ret)),
                _colorize(f"{relret:+.2f}%", _color_by_sign(relret)),
                relret,
                idx,
            )
        )

    def _sort_key(row: tuple[str, str, str, str, float | None, int]) -> tuple[int, float, int]:
        """Sort relret rows by strongest outperformance first."""
        _symbol, _ret_txt, _bench_txt, _relret_txt, relret, original_idx = row
        if relret is None:
            return (1, 0.0, original_idx)
        return (0, -relret, original_idx)

    for symbol, ret_txt, bench_txt, relret_txt, _relret, _idx in sorted(rows, key=_sort_key):
        print(" ".join([_pad_cell(symbol, 16), _pad_cell(ret_txt, 10, "right"), _pad_cell(bench_txt, 10, "right"), _pad_cell(relret_txt, 10, "right")]))

    if active_watchlist and explicit_symbols is None:
        # Keep portfolio summary fixed at the end so symbol ranking remains purely per-stock.
        print()
        if valid_returns:
            ew_return = sum(valid_returns) / len(valid_returns)
            ew_relret = ew_return - bench_ret
            ew_return_txt = _colorize(f"{ew_return:+.2f}%", _color_by_sign(ew_return))
            ew_relret_txt = _colorize(f"{ew_relret:+.2f}%", _color_by_sign(ew_relret))
            bench_txt = _colorize(f"{bench_ret:+.2f}%", _color_by_sign(bench_ret))
        else:
            ew_return_txt = "n/a"
            ew_relret_txt = "n/a"
            bench_txt = _colorize(f"{bench_ret:+.2f}%", _color_by_sign(bench_ret))
        print(
            " ".join(
                [
                    _pad_cell("WATCHLIST(EW)", 16),
                    _pad_cell(ew_return_txt, 10, "right"),
                    _pad_cell(bench_txt, 10, "right"),
                    _pad_cell(ew_relret_txt, 10, "right"),
                ]
            )
        )
    return 0


def _daily_return_series_for_period(symbol: str, period_token: str) -> pd.Series | None:
    """Return aligned daily percent-change series for correlation calculations."""
    points, closes = _close_series_for_period(symbol, period_token=period_token)
    if len(points) < 2 or len(points) != len(closes):
        return None
    idx = [int(point.timestamp()) for point in points]
    series = pd.Series(closes, index=idx, dtype="float64").groupby(level=0).last().pct_change().dropna()
    return series if not series.empty else None


def _print_corr_snapshot(
    current_symbol: str | None,
    active_watchlist: str | None,
    period_token: str,
    explicit_symbols: list[str] | None = None,
) -> int:
    """Print a compact correlation summary for symbols in active context or explicit basket."""
    if explicit_symbols is not None:
        symbols = _resolve_analytics_symbol_inputs(explicit_symbols)
        if symbols is None:
            return 3
        title = "Explicit symbols"
    else:
        title, symbols = _moves_targets_for_context(current_symbol=current_symbol, active_watchlist=active_watchlist)
        if title is None or symbols is None:
            return 3
    if len(symbols) < 2:
        print("corr needs at least two symbols in the current context.", file=sys.stderr)
        return 3

    aligned: list[pd.Series] = []
    names: list[str] = []
    for symbol in symbols:
        series = _daily_return_series_for_period(symbol, period_token=period_token)
        if series is None:
            continue
        aligned.append(series.rename(symbol))
        names.append(symbol)
    if len(aligned) < 2:
        print("Not enough overlapping return series to build correlation matrix.", file=sys.stderr)
        return 3

    frame = pd.concat(aligned, axis=1, join="inner").dropna()
    if frame.shape[0] < 2 or frame.shape[1] < 2:
        print("Not enough overlapping return series to build correlation matrix.", file=sys.stderr)
        return 3

    corr = frame.corr(numeric_only=True)
    pairs: list[tuple[str, str, float]] = []
    columns = corr.columns.tolist()
    for left_idx in range(len(columns)):
        for right_idx in range(left_idx + 1, len(columns)):
            left = columns[left_idx]
            right = columns[right_idx]
            value = float(corr.loc[left, right])
            pairs.append((left, right, value))
    if not pairs:
        print("Not enough symbol pairs to summarize correlation.", file=sys.stderr)
        return 3

    def _format_pair_row(left: str, right: str, value: float) -> str:
        """Format one correlation pair row with sign-aware color."""
        pair_label = f"{left} <-> {right}"
        color = "green" if value >= 0 else "red"
        return f"{_pad_cell(pair_label, 36)} {_colorize(f'{value:+.2f}', color)}"

    def _print_section(header: str, rows: list[tuple[str, str, float]]) -> None:
        """Print one summary section, keeping output compact on narrow terminals."""
        print()
        print(header)
        if not rows:
            print("n/a")
            return
        for left, right, value in rows:
            print(_format_pair_row(left, right, value))

    # Choose fixed, compact section sizes to keep corr usable in narrow terminals.
    top_n = 5
    positives = sorted((row for row in pairs if row[2] >= 0), key=lambda row: row[2], reverse=True)[:top_n]
    negatives = sorted((row for row in pairs if row[2] < 0), key=lambda row: row[2])[:top_n]
    used_keys = {(left, right) for left, right, _value in [*positives, *negatives]}
    near_zero = sorted((row for row in pairs if (row[0], row[1]) not in used_keys), key=lambda row: abs(row[2]))[:top_n]

    print()
    print(f"Correlation Summary ({period_token.upper()}) - {title}")
    print(f"Universe: {len(symbols)} symbols | overlap points: {frame.shape[0]}")
    _print_section("Most Positive Pairs", positives)
    _print_section("Most Negative Pairs", negatives)
    _print_section("Near-Zero Pairs (Diversifiers)", near_zero)
    return 0


def _count_green_days_from_closes(closes: list[float | None], days: int) -> int | None:
    """Count positive day-over-day moves within the trailing `days` window."""
    finite_closes = [float(close) for close in closes if isinstance(close, (int, float)) and math.isfinite(float(close))]
    if len(finite_closes) < days + 1:
        return None
    moves = finite_closes[-(days + 1) :]
    green_days = 0
    for idx in range(1, len(moves)):
        if moves[idx] > moves[idx - 1]:
            green_days += 1
    return green_days


def _moves_targets_for_context(
    current_symbol: str | None,
    active_watchlist: str | None,
) -> tuple[str, list[str]] | tuple[None, None]:
    """Resolve `moves` target symbols from watchlist mode or active index/symbol context."""
    if active_watchlist:
        symbols = _watchlist_symbols(active_watchlist)
        if symbols is None:
            print(f"Watchlist '{active_watchlist}' not found.", file=sys.stderr)
            return None, None
        if not symbols:
            print(f"Watchlist '{active_watchlist}' is empty. Use `add <code>` in this mode.", file=sys.stderr)
            return None, None
        return f"Watchlist {active_watchlist}", list(dict.fromkeys(symbols))

    if not current_symbol:
        print("No active symbol. Enter a symbol first.", file=sys.stderr)
        return None, None

    if _is_known_index_symbol(current_symbol):
        universe = _snap_universe_for_symbol(current_symbol)
        # For indices without configured constituents, still allow symbol-level moves/trend.
        if universe is None:
            return current_symbol.upper(), [current_symbol]
        label, members = universe
        return label, list(dict.fromkeys(members))

    return current_symbol.upper(), [current_symbol]


def _resolve_analytics_symbol_inputs(symbol_inputs: list[str]) -> list[str] | None:
    """Resolve and deduplicate explicit analytics symbol inputs using regular symbol resolver."""
    resolved_symbols: list[str] = []
    for token in symbol_inputs:
        resolved_symbol, info = _resolve_symbol_with_fallback(token)
        if info is None:
            print(f"Could not resolve symbol '{token}'.", file=sys.stderr)
            return None
        resolved_symbols.append(resolved_symbol)
    return list(dict.fromkeys(resolved_symbols))


def _print_moves_snapshot(
    current_symbol: str | None,
    active_watchlist: str | None,
    period_token: str,
    explicit_symbols: list[str] | None = None,
) -> int:
    """Print per-symbol directional move dots for active context or explicit `on` basket."""
    if explicit_symbols is not None:
        symbols = _resolve_analytics_symbol_inputs(explicit_symbols)
        if symbols is None:
            return 3
        title = "Explicit symbols"
    else:
        title, symbols = _moves_targets_for_context(current_symbol=current_symbol, active_watchlist=active_watchlist)
        if title is None or symbols is None:
            return 3

    days = _moves_days_for_period(period_token)
    period_label = period_token.upper()
    print()
    print(f"Moves ({period_label}) - {title}")
    print(f"{'Symbol':<16} {f'{period_label} Moves':<12} Dots")

    rows: list[tuple[str, str, int | None, int]] = []
    lookback_days = max((days + 1) * 3, 30)
    for idx, symbol in enumerate(symbols):
        _points, closes = _fetch_close_points_for_token(symbol, f"{lookback_days}d", "1d")
        dots = quote_tools.recent_direction_dots_from_points(closes=closes, days=days, colorize=_colorize)
        green_days = _count_green_days_from_closes(closes=closes, days=days)
        rows.append((symbol, dots or "n/a", green_days, idx))

    def _moves_sort_key(row: tuple[str, str, int | None, int]) -> tuple[int, int, int]:
        """Sort by green-day count (desc), with unavailable rows last and stable ties."""
        _symbol, _dots, green_days, original_idx = row
        # Keep n/a rows after ranked rows so high-confidence movers stay at top.
        if green_days is None:
            return (1, 0, original_idx)
        return (0, -green_days, original_idx)

    for symbol, dots_txt, _green_days, _idx in sorted(rows, key=_moves_sort_key):
        print(f"{symbol:<16} {f'{period_label} Moves':<12} {dots_txt}")
    return 0


def _trend_score_for_symbol(symbol: str) -> tuple[float | None, float | None]:
    """Compute trend score tuple `(score, total)` for one symbol using current daily context."""
    points, closes = _fetch_close_points_for_token(symbol, period_token="1y", interval="1d")
    if not closes:
        return None, None
    signal = quote_tools.quote_signal_snapshot(points=points, closes=closes, volumes=[])
    score_raw = signal.get("trend_score")
    total_raw = signal.get("trend_total")
    try:
        score = float(score_raw) if score_raw is not None else None
        total = float(total_raw) if total_raw is not None else None
    except (TypeError, ValueError):
        return None, None
    return score, total


def _print_trend_snapshot(
    current_symbol: str | None,
    active_watchlist: str | None,
    explicit_symbols: list[str] | None = None,
) -> int:
    """Print per-symbol trend scores sorted from strongest to weakest."""
    if explicit_symbols is not None:
        symbols = _resolve_analytics_symbol_inputs(explicit_symbols)
        if symbols is None:
            return 3
        title = "Explicit symbols"
    else:
        title, symbols = _moves_targets_for_context(current_symbol=current_symbol, active_watchlist=active_watchlist)
        if title is None or symbols is None:
            return 3

    print()
    print(f"Trend (Current) - {title}")
    print(f"{'Symbol':<16} {'Trend Score':<16}")

    rows: list[tuple[str, str, float | None, int]] = []
    for idx, symbol in enumerate(symbols):
        score, total = _trend_score_for_symbol(symbol=symbol)
        if score is None or total is None or total <= 0:
            rows.append((symbol, "n/a", None, idx))
            continue
        rows.append((symbol, f"{score:.1f}/{total:.1f}", score / total, idx))

    def _trend_sort_key(row: tuple[str, str, float | None, int]) -> tuple[int, float, int]:
        """Sort ranked trend rows descending, with unavailable rows at the bottom."""
        _symbol, _score_txt, ratio, original_idx = row
        # Keep missing signals last so available trend ranks are easy to scan.
        if ratio is None:
            return (1, 0.0, original_idx)
        return (0, -ratio, original_idx)

    for symbol, score_txt, _ratio, _idx in sorted(rows, key=_trend_sort_key):
        print(f"{symbol:<16} {score_txt:<16}")
    return 0


def _run_repl(
    start_input_symbol: str | None,
    start_resolved_symbol: str | None,
    start_info: dict[str, Any] | None,
    width: int,
    height: int,
) -> int:
    """Run interactive tickertrail session with quote/chart/table commands."""
    _enable_repl_history()
    current_symbol = start_resolved_symbol
    current_info = start_info
    active_watchlist: str | None = None
    mode_return_target: tuple[str, str, dict[str, Any] | None] | None = None
    last_view_kind = "quote" if current_symbol else None
    last_view_args: dict[str, Any] = {}

    if current_symbol:
        code = _print_quote(
            start_input_symbol or current_symbol,
            current_symbol,
            include_after_hours=True,
            preloaded_info=current_info,
        )
        if code != 0:
            return code
    report_pending = False

    def _print_help(topic: str | None = None) -> None:
        """Print organized REPL help with command-level usage details."""

        def _print_command_help(
            command: str,
            aliases: list[str],
            usage_lines: list[str],
            detail_lines: list[str],
            example_lines: list[str],
            default_lines: list[str] | None = None,
        ) -> None:
            """Print one command reference block."""
            alias_txt = ", ".join(aliases) if aliases else "none"
            print(f"\nCommand: {command}")
            print(f"Aliases: {alias_txt}")
            print("Usage:")
            for line in usage_lines:
                print(f"  {line}")
            print("Details:")
            for line in detail_lines:
                print(f"  - {line}")
            print("Defaults:")
            if default_lines:
                for line in default_lines:
                    print(f"  - {line}")
            else:
                print("  - none")
            print("Examples:")
            for line in example_lines:
                print(f"  {line}")
            print()

        def _print_overview() -> None:
            """Print top-level organized command map plus starter examples."""
            print("\nTickertrail Help")
            print("===============")
            print("Use `help <command>` for command-level details.")
            print("Use `help core|chart|table|watchlist|index` for category summaries.")
            print()
            print("Core Commands:")
            print("  h | help [topic|command]    Show organized help")
            print("  quote | q                   Show current symbol/index quote")
            print("  news <code>                 Show recent Yahoo headlines")
            print("  quit | exit                 Exit")
            print("  cls | clear                 Clear terminal")
            print("  reload | r                  Refresh quote + replay last chart/table")
            print("  cd ..                       Return to last index/watchlist mode")
            print("  !<shell-cmd>                Run shell command")
            print("  cache                       Show today's persisted history cache summary")
            print("  cache clear                 Clear today's persisted history cache")
            print()
            print("Analytics:")
            print("  move [period]               Directional move-dot board (alias: moves)")
            print("  trend                       Current trend-score board (alias: trends)")
            print("  relret [period]             Relative-return ranking (alias: rr)")
            print("  corr [period]               Correlation summary")
            print("  cmp <symbols...> [period [agg]]   Rebased compare table")
            print()
            print("Market + Discovery:")
            print("  <symbol>                    Switch active symbol + quote")
            print("  code <query>                Fuzzy ticker lookup")
            print("  news <code>                 Recent Yahoo symbol headlines")
            print("  index | index list          Index board and symbol catalog")
            print("  snap                        Active index/watchlist snapshot")
            print()
            print("Charts + Tables:")
            print("  chart swing ... | c ...     Swing chart")
            print("  chart intra ... | cc ...    Intraday chart")
            print("  table swing ... | t ...     Swing rebased table")
            print("  table intra ... | tt ...    Intraday rebased table")
            print("  <period>                    Shortcut for swing chart period")
            print()
            print("Watchlists:")
            print("  watchlist create|list|open|delete|merge ...")
            print("  wl ...                      Alias namespace")
            print("  add|delete|list|ll          Watchlist mode symbol operations")
            print()
            print("Quick Start Examples:")
            print("  help move")
            print("  help watchlist open")
            print("  news infy")
            print("  chart swing nifty 3mo w")
            print("  table intra nifty 15m")
            print("  move 1mo")
            print("  trend")
            print("  relret 3mo")
            print("  corr")
            print("  watchlist create swing")
            print("  watchlist open swing")
            print("  add tcs infy reliance")
            print("  snap")
            print()

        def _print_topic_summary(normalized_topic: str) -> bool:
            """Print one category summary and return True when handled."""
            if normalized_topic in {"core", "general"}:
                print("\nCore Commands:")
                print("  h | help [topic|command]")
                print("  quote | q")
                print("  quit | exit")
                print("  cls | clear")
                print("  reload | r")
                print("  cd ..")
                print("  !<shell-cmd>")
                print("  cache")
                print("  cache clear")
                print("  code <query>")
                print("  news <code>")
                print("  cmp <symbols...> [period [agg]]")
                print("  <period>")
                print("  <symbol>")
                print("\nExamples:")
                print("  help relret")
                print("  code national thermal")
                print("  news infy")
                print("  cmp nifty goldbees hdfcbank 1y w")
                print()
                return True
            if normalized_topic in {"index"}:
                print("\nIndex Commands:")
                print("  index")
                print("  index list")
                print("  snap")
                print("  move [period]")
                print("  trend")
                print("  relret [period] (alias: rr)")
                print("  corr [period]")
                print("\nExamples:")
                print("  index")
                print("  index list")
                print("  nifty")
                print("  move 1mo")
                print()
                return True
            if normalized_topic in {"chart"}:
                print("\nChart Commands:")
                print("  chart swing [<code>] [<period>]")
                print("  chart swing [<code>] - <period> [agg]")
                print("  chart intra [<code>] [<1m|5m|15m|30m|1hr>]")
                print("  c ...")
                print("  cc ...")
                print("\nExamples:")
                print("  help c")
                print("  chart swing nifty 6mo")
                print("  c nifty - 2y mo")
                print("  cc banknifty 5m")
                print()
                return True
            if normalized_topic in {"table"}:
                print("\nTable Commands:")
                print("  table swing [<code>] [<period>]")
                print("  table swing [<code>] - <period> [agg]")
                print("  table intra [<code>] [<1m|5m|15m|30m|1hr>]")
                print("  table intra [<code>] - <period> [agg]")
                print("  t ...")
                print("  tt ...")
                print("\nExamples:")
                print("  help tt")
                print("  table swing nifty - 2y mo")
                print("  t nifty")
                print("  tt 15m")
                print()
                return True
            if normalized_topic in {"watchlist", "wl"}:
                print("\nWatchlist Commands:")
                print("  watchlist create <name> | wl create <name>")
                print("  watchlist list | wl list")
                print("  watchlist open <name> | wl open <name>")
                print("  watchlist delete <name> | wl delete <name>")
                print("  watchlist merge <wl1> <wl2> <target> | wl merge ...")
                print("  watchlist <name> | wl <name>")
                print("  watchlist   # exit mode")
                print("  add <codes...>")
                print("  delete <codes...>")
                print("  list | ll")
                print("  snap")
                print("\nExamples:")
                print("  watchlist create swing")
                print("  watchlist open swing")
                print("  add tcs infy reliance")
                print("  move")
                print()
                return True
            return False

        normalized = " ".join((topic or "").strip().lower().split())
        if not normalized:
            _print_overview()
            return

        if _print_topic_summary(normalized):
            return

        command_aliases: dict[str, str] = {
            "h": "help",
            "help": "help",
            "q": "quote",
            "quote": "quote",
            "quit": "quit",
            "exit": "quit",
            "cls": "clear",
            "clear": "clear",
            "cache": "cache",
            "cache clear": "cache clear",
            "reload": "reload",
            "r": "reload",
            "refresh": "reload",
            "!": "shell",
            "!<shell-cmd>": "shell",
            "code": "code",
            "news": "news",
            "index": "index",
            "index list": "index list",
            "snap": "snap",
            "move": "move",
            "moves": "move",
            "trend": "trend",
            "trends": "trend",
            "relret": "relret",
            "rr": "relret",
            "corr": "corr",
            "cmp": "cmp",
            "chart": "chart",
            "chart swing": "chart swing",
            "chart intra": "chart intra",
            "c": "c",
            "cc": "cc",
            "table": "table",
            "table swing": "table swing",
            "table intra": "table intra",
            "t": "t",
            "tt": "tt",
            "watchlist": "watchlist",
            "watchlist create": "watchlist create",
            "watchlist list": "watchlist list",
            "watchlist open": "watchlist open",
            "watchlist delete": "watchlist delete",
            "watchlist merge": "watchlist merge",
            "wl": "watchlist",
            "wl create": "watchlist create",
            "wl list": "watchlist list",
            "wl open": "watchlist open",
            "wl delete": "watchlist delete",
            "wl merge": "watchlist merge",
            "add": "add",
            "delete": "delete",
            "list": "list",
            "ll": "list",
            "<period>": "<period>",
            "<symbol>": "<symbol>",
        }
        canonical = command_aliases.get(normalized)
        if canonical is None:
            # Keep unknown-topic diagnostics explicit so users can discover the grammar quickly.
            print(
                f"Unknown help topic '{topic}'. Try: help move | help trend | help chart swing | help watchlist open",
                file=sys.stderr,
            )
            return

        if canonical == "help":
            _print_command_help(
                command="help",
                aliases=["h"],
                usage_lines=["help", "help <topic>", "help <command>"],
                detail_lines=[
                    "Top-level help is organized by categories and quick-start examples.",
                    "Topics: core, chart, table, watchlist, index.",
                    "Command-level help supports canonical commands and aliases.",
                ],
                example_lines=["help", "help core", "help move", "help watchlist merge"],
            )
            return
        if canonical == "quote":
            _print_command_help(
                command="quote",
                aliases=["q"],
                usage_lines=["quote"],
                detail_lines=[
                    "Render quote for active stock/index symbol.",
                    "Unavailable in watchlist mode; exit watchlist or switch to symbol mode first.",
                ],
                default_lines=["symbol: current active symbol"],
                example_lines=["quote", "q"],
            )
            return
        if canonical == "quit":
            _print_command_help(
                command="quit",
                aliases=["exit"],
                usage_lines=["quit", "exit"],
                detail_lines=["Exit REPL immediately."],
                example_lines=["quit"],
            )
            return
        if canonical == "clear":
            _print_command_help(
                command="clear",
                aliases=["cls"],
                usage_lines=["clear"],
                detail_lines=["Clear terminal screen and keep REPL session active."],
                example_lines=["clear"],
            )
            return
        if canonical == "cache":
            _print_command_help(
                command="cache",
                aliases=[],
                usage_lines=["cache", "cache clear"],
                detail_lines=[
                    "Shows today's persisted history cache summary (path, entry count, kinds, symbols).",
                    "`cache clear` deletes only today's persisted history cache bucket.",
                ],
                example_lines=["cache", "cache clear"],
            )
            return
        if canonical == "cache clear":
            _print_command_help(
                command="cache clear",
                aliases=[],
                usage_lines=["cache clear"],
                detail_lines=["Clears only today's persisted history cache bucket."],
                example_lines=["cache clear"],
            )
            return
        if canonical == "reload":
            _print_command_help(
                command="reload",
                aliases=["r", "refresh"],
                usage_lines=["reload"],
                detail_lines=["Refresh active quote and replay last non-quote chart/table/compare view."],
                example_lines=["reload", "r"],
            )
            return
        if canonical == "shell":
            _print_command_help(
                command="!<shell-cmd>",
                aliases=[],
                usage_lines=["!<shell-cmd>"],
                detail_lines=["Run shell command in underlying terminal context."],
                example_lines=["!pwd", "!ls -la data"],
            )
            return
        if canonical == "code":
            _print_command_help(
                command="code",
                aliases=[],
                usage_lines=["code <query>"],
                detail_lines=["Fuzzy-lookup likely ticker codes using local NSE universe data."],
                example_lines=["code national thermal", "code bank of baroda"],
            )
            return
        if canonical == "news":
            _print_command_help(
                command="news",
                aliases=[],
                usage_lines=["news <code>"],
                detail_lines=[
                    "Resolve symbol and print recent Yahoo Finance news headlines.",
                    "Uses Yahoo `Ticker.news`; availability varies by symbol and region.",
                ],
                default_lines=["headline limit: 5"],
                example_lines=["news infy", "news aapl"],
            )
            return
        if canonical == "index":
            _print_command_help(
                command="index",
                aliases=[],
                usage_lines=["index"],
                detail_lines=["Show India and global index board with quote snapshot."],
                example_lines=["index"],
            )
            return
        if canonical == "index list":
            _print_command_help(
                command="index list",
                aliases=[],
                usage_lines=["index list"],
                detail_lines=["Show curated index symbol catalog without live quote fetch."],
                example_lines=["index list"],
            )
            return
        if canonical == "snap":
            _print_command_help(
                command="snap",
                aliases=[],
                usage_lines=["snap"],
                detail_lines=[
                    "In watchlist mode, shows watchlist snapshot board.",
                    "Otherwise, in index mode/symbol context, shows active index constituents snapshot.",
                ],
                example_lines=["watchlist open swing", "snap", "nifty", "snap"],
            )
            return
        if canonical == "move":
            _print_command_help(
                command="move",
                aliases=["moves"],
                usage_lines=[
                    f"move [{_ANALYTICS_PERIOD_HINT}]",
                    f"move on <code1> <code2> ... [{_ANALYTICS_PERIOD_HINT}]",
                ],
                detail_lines=[
                    "Shows directional dots per symbol for active context (symbol/index/watchlist).",
                    "Use `on <codes...>` to override active context with explicit symbols.",
                    "Periods accept Nd, Nmo (<12), or Ny (for example: 5d, 2mo, 3y).",
                    "Rows are sorted by max green days to least green days.",
                ],
                default_lines=["period: 1mo"],
                example_lines=["move", "moves 3mo", "move on infy tcs reliance 3mo"],
            )
            return
        if canonical == "trend":
            _print_command_help(
                command="trend",
                aliases=["trends"],
                usage_lines=["trend", "trend on <code1> <code2> ..."],
                detail_lines=[
                    "Shows current trend score per symbol as score/total.",
                    "Use `on <codes...>` to override active context with explicit symbols.",
                    "Rows are sorted highest trend score ratio first.",
                ],
                default_lines=["arguments: none"],
                example_lines=["trend", "trend on hdfcbank icicibank kotakbank"],
            )
            return
        if canonical == "relret":
            _print_command_help(
                command="relret",
                aliases=["rr"],
                usage_lines=[
                    f"relret [{_ANALYTICS_PERIOD_HINT}] [vs <benchmark> [{_ANALYTICS_PERIOD_HINT}]]",
                    f"relret on <code1> <code2> ... [{_ANALYTICS_PERIOD_HINT}] [vs <benchmark> [{_ANALYTICS_PERIOD_HINT}]]",
                ],
                detail_lines=[
                    "Shows symbol return, benchmark return, and relative return.",
                    "Use `on <codes...>` to override active context with explicit symbols.",
                    "Use `vs <benchmark>` to override benchmark selection.",
                    "Periods accept Nd, Nmo (<12), or Ny (for example: 5d, 2mo, 3y).",
                    "Rows are sorted by strongest outperformance first.",
                ],
                default_lines=["period: 1mo"],
                example_lines=["relret", "rr 3mo", "relret on tcs infy hcltech 6mo vs it"],
            )
            return
        if canonical == "corr":
            _print_command_help(
                command="corr",
                aliases=[],
                usage_lines=[
                    f"corr [{_ANALYTICS_PERIOD_HINT}]",
                    f"corr on <code1> <code2> ... [{_ANALYTICS_PERIOD_HINT}]",
                ],
                detail_lines=[
                    "Shows compact correlation summary for active context.",
                    "Use `on <codes...>` to override active context with explicit symbols.",
                    "Periods accept Nd, Nmo (<12), or Ny (for example: 5d, 2mo, 3y).",
                    "Sections: most positive pairs, most negative pairs, near-zero diversifier pairs.",
                ],
                default_lines=["period: 1mo"],
                example_lines=["corr", "corr 6mo", "corr on tcs infy reliance 3mo"],
            )
            return
        if canonical == "cmp":
            _print_command_help(
                command="cmp",
                aliases=[],
                usage_lines=["cmp <symbol1> <symbol2> [symbolN ...] [period [agg]]"],
                detail_lines=["Compare multiple symbols in a single rebased table."],
                default_lines=["period: 6mo", "aggregation: auto (from period)"],
                example_lines=["cmp nifty goldbees hdfcbank 3y w", "cmp tcs infy 1y"],
            )
            return
        if canonical == "chart":
            _print_command_help(
                command="chart",
                aliases=[],
                usage_lines=["chart swing ...", "chart intra ..."],
                detail_lines=["Canonical chart family; pick swing or intra sub-command."],
                example_lines=["help chart swing", "help chart intra"],
            )
            return
        if canonical == "chart swing":
            _print_command_help(
                command="chart swing",
                aliases=["c"],
                usage_lines=["chart swing [<code>] [<period>]", "chart swing [<code>] - <period> [agg]"],
                detail_lines=["Render swing chart with period and optional aggregation override."],
                default_lines=["period: 6mo", "aggregation: auto (from period)", "symbol: current active symbol"],
                example_lines=["chart swing nifty 3mo", "c nifty - 2y mo", "c 1y"],
            )
            return
        if canonical == "chart intra":
            _print_command_help(
                command="chart intra",
                aliases=["cc"],
                usage_lines=["chart intra [<code>] [<1m|5m|15m|30m|1hr>]"],
                detail_lines=["Render intraday chart with minute interval."],
                default_lines=["interval: 5m", "symbol: current active symbol"],
                example_lines=["chart intra banknifty 5m", "cc 1m", "cc nifty 1hr"],
            )
            return
        if canonical == "c":
            _print_command_help(
                command="c",
                aliases=["chart swing"],
                usage_lines=["c [<code>] [<period>]", "c [<code>] - <period> [agg]"],
                detail_lines=["Short alias for swing chart command family."],
                default_lines=["period: 6mo", "aggregation: auto (from period)", "symbol: current active symbol"],
                example_lines=["c", "c 2y", "c nifty - 2y mo"],
            )
            return
        if canonical == "cc":
            _print_command_help(
                command="cc",
                aliases=["chart intra"],
                usage_lines=["cc [<code>] [<1m|5m|15m|30m|1hr>]"],
                detail_lines=["Short alias for intraday chart command family."],
                default_lines=["interval: 5m", "symbol: current active symbol"],
                example_lines=["cc", "cc 30m", "cc nifty 1hr"],
            )
            return
        if canonical == "table":
            _print_command_help(
                command="table",
                aliases=[],
                usage_lines=["table swing ...", "table intra ..."],
                detail_lines=["Canonical table family; pick swing or intra sub-command."],
                example_lines=["help table swing", "help table intra"],
            )
            return
        if canonical == "table swing":
            _print_command_help(
                command="table swing",
                aliases=["t"],
                usage_lines=["table swing [<code>] [<period>]", "table swing [<code>] - <period> [agg]"],
                detail_lines=["Render swing rebased stock-vs-benchmark table."],
                default_lines=["period: 6mo", "aggregation: auto (from period)", "symbol: current active symbol"],
                example_lines=["table swing", "table swing nifty - 2y mo", "t nifty 1y"],
            )
            return
        if canonical == "table intra":
            _print_command_help(
                command="table intra",
                aliases=["tt"],
                usage_lines=["table intra [<code>] [<1m|5m|15m|30m|1hr>]", "table intra [<code>] - <period> [agg]"],
                detail_lines=["Render intraday-first rebased table with minute interval controls."],
                default_lines=["interval: 5m", "symbol: current active symbol"],
                example_lines=["table intra nifty 1hr", "tt 30m", "tt - 2y mo"],
            )
            return
        if canonical == "t":
            _print_command_help(
                command="t",
                aliases=["table swing"],
                usage_lines=["t [<code>] [<period>]", "t [<code>] - <period> [agg]"],
                detail_lines=["Short alias for swing table command family."],
                default_lines=["period: 6mo", "aggregation: auto (from period)", "symbol: current active symbol"],
                example_lines=["t", "t nifty", "t nifty - 2y mo"],
            )
            return
        if canonical == "tt":
            _print_command_help(
                command="tt",
                aliases=["table intra"],
                usage_lines=["tt [<code>] [<1m|5m|15m|30m|1hr>]", "tt [<code>] - <period> [agg]"],
                detail_lines=["Short alias for intraday-first table command family."],
                default_lines=["interval: 5m", "symbol: current active symbol"],
                example_lines=["tt", "tt 1hr", "tt nifty - 2y mo"],
            )
            return
        if canonical == "watchlist":
            _print_command_help(
                command="watchlist",
                aliases=["wl"],
                usage_lines=[
                    "watchlist",
                    "watchlist <name>",
                    "watchlist open <name>",
                    "watchlist create|list|delete|merge ...",
                ],
                detail_lines=[
                    "Canonical watchlist command family.",
                    "Bare `watchlist` exits active watchlist mode.",
                    "`watchlist <name>` is shorthand for `watchlist open <name>`.",
                ],
                example_lines=["watchlist list", "watchlist open swing", "watchlist"],
            )
            return
        if canonical == "watchlist create":
            _print_command_help(
                command="watchlist create",
                aliases=["wl create"],
                usage_lines=["watchlist create <name>"],
                detail_lines=["Create a new empty watchlist."],
                example_lines=["watchlist create swing"],
            )
            return
        if canonical == "watchlist list":
            _print_command_help(
                command="watchlist list",
                aliases=["wl list", "wl"],
                usage_lines=["watchlist list"],
                detail_lines=["List all watchlists with symbol counts."],
                example_lines=["watchlist list", "wl"],
            )
            return
        if canonical == "watchlist open":
            _print_command_help(
                command="watchlist open",
                aliases=["watchlist <name>", "wl open", "wl <name>"],
                usage_lines=["watchlist open <name>", "watchlist <name>"],
                detail_lines=["Enter watchlist mode; prompt changes to `<name>>`."],
                example_lines=["watchlist open swing", "wl swing"],
            )
            return
        if canonical == "watchlist delete":
            _print_command_help(
                command="watchlist delete",
                aliases=["wl delete"],
                usage_lines=["watchlist delete <name>"],
                detail_lines=["Delete one watchlist by name."],
                example_lines=["watchlist delete swing"],
            )
            return
        if canonical == "watchlist merge":
            _print_command_help(
                command="watchlist merge",
                aliases=["wl merge"],
                usage_lines=["watchlist merge <wl1> <wl2> <target>"],
                detail_lines=["Merge two watchlists into target with de-duplicated stable order."],
                example_lines=["watchlist merge swing momentum core"],
            )
            return
        if canonical == "add":
            _print_command_help(
                command="add",
                aliases=[],
                usage_lines=["add <codes...>"],
                detail_lines=["Add validated symbols to active watchlist mode."],
                example_lines=["add tcs infy reliance"],
            )
            return
        if canonical == "delete":
            _print_command_help(
                command="delete",
                aliases=[],
                usage_lines=["delete <codes...>"],
                detail_lines=["Delete symbols from active watchlist mode."],
                example_lines=["delete infy"],
            )
            return
        if canonical == "list":
            _print_command_help(
                command="list",
                aliases=["ll"],
                usage_lines=["list"],
                detail_lines=["List symbols in active watchlist mode."],
                example_lines=["list", "ll"],
            )
            return
        if canonical == "<period>":
            _print_command_help(
                command="<period>",
                aliases=[],
                usage_lines=["<period>"],
                detail_lines=["Shortcut for swing chart period token (for example 6mo, 1y, 2y)."],
                default_lines=["applies to: swing chart shortcut"],
                example_lines=["6mo", "1y"],
            )
            return
        if canonical == "<symbol>":
            _print_command_help(
                command="<symbol>",
                aliases=[],
                usage_lines=["<symbol>"],
                detail_lines=["Switch active symbol (or index alias in index mode) and print quote."],
                example_lines=["reliance", "nifty", "it"],
            )
            return

    while True:
        if report_pending:
            _print_network_call_metrics()
            report_pending = False
        try:
            raw = input(_prompt_for_context(current_symbol, active_watchlist))
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print()
            return 0

        cmd = raw.strip()
        # Users sometimes paste prompt fragments (e.g. `tickertrail>cnxit> snap`); keep last command token.
        if ">" in cmd and cmd.lower().startswith("tickertrail>"):
            cmd = cmd.split(">")[-1].strip()
        if not cmd:
            continue
        _reset_network_call_metrics()
        report_pending = True
        lower = cmd.lower()
        if lower in {"quit", "exit"}:
            _print_network_call_metrics()
            return 0
        if lower == "cd ..":
            # Lightweight mode-navigation return: restores previous mode without symbol re-resolution.
            if mode_return_target is None:
                print("No previous index/watchlist mode to return to.", file=sys.stderr)
                continue
            target_kind, target_value, target_info = mode_return_target
            if target_kind == "watchlist":
                if _watchlist_symbols(target_value) is None:
                    print(f"Watchlist '{target_value}' not found.", file=sys.stderr)
                    continue
                active_watchlist = target_value
                print(f"Returned to watchlist mode '{target_value}'.")
                continue
            if target_kind == "index":
                current_symbol = target_value
                current_info = target_info
                active_watchlist = None
                if isinstance(current_info, dict) and _has_quote_data(current_info):
                    _print_quote(current_symbol, current_symbol, include_after_hours=True, preloaded_info=current_info)
                else:
                    print(f"Returned to index mode '{current_symbol}'. Use `quote` to refresh quote.")
                last_view_kind = "quote"
                last_view_args = {}
                continue
            print("No previous index/watchlist mode to return to.", file=sys.stderr)
            continue
        if lower in {"quote", "q"} or lower.startswith("quote "):
            if lower.startswith("quote ") or (lower.startswith("q ") and lower != "q"):
                print("Usage: quote", file=sys.stderr)
                continue
            if active_watchlist:
                print("quote is unavailable in watchlist mode. Exit watchlist mode first.", file=sys.stderr)
                continue
            if not current_symbol:
                print("No active symbol. Enter a symbol first.", file=sys.stderr)
                continue
            refreshed_info = _get_quote_payload(current_symbol)
            if not _has_quote_data(refreshed_info) and _is_index_context_symbol(current_symbol):
                fallback_info = _index_quote_fallback_payload(current_symbol)
                if fallback_info is not None:
                    refreshed_info = fallback_info
            if not _has_quote_data(refreshed_info):
                print(f"Could not fetch quote for '{current_symbol}'.", file=sys.stderr)
                continue
            current_info = refreshed_info
            _print_quote(current_symbol, current_symbol, include_after_hours=True, preloaded_info=current_info)
            last_view_kind = "quote"
            last_view_args = {}
            continue
        if lower in {"h", "help"}:
            _print_help(None)
            continue
        if lower.startswith("help "):
            _print_help(cmd.split(maxsplit=1)[1].strip())
            continue
        if lower in {"cls", "clear"}:
            # ANSI clear-screen + cursor-home; keep REPL session active.
            print("\033[2J\033[H", end="")
            continue
        if lower == "cache" or lower.startswith("cache "):
            # Decision block: keep cache grammar explicit to avoid ambiguous symbol parsing.
            if lower == "cache":
                _print_history_cache_summary()
            elif lower == "cache clear":
                # Keep cache control explicit and scoped: only today's history cache bucket is flushed.
                deleted = price_history.clear_history_cache_today()
                if deleted:
                    print("Cleared today's history cache.")
                else:
                    print("Today's history cache is already empty.")
            else:
                print("Usage: cache | cache clear", file=sys.stderr)
            continue
        if cmd.startswith("!"):
            shell_cmd = cmd[1:].strip()
            if not shell_cmd:
                print("Usage: !<shell-cmd>", file=sys.stderr)
                continue
            # Shell passthrough intentionally mirrors terminal behavior for quick ad-hoc tasks.
            subprocess.run(shell_cmd, shell=True, check=False)
            continue
        if lower == "wl":
            # Bare wl is a convenience alias for `wl list`.
            cmd = "wl list"
            lower = cmd.lower()
        if lower == "watchlist":
            # Bare watchlist token exits watchlist mode and returns to symbol-mode prompt.
            if active_watchlist is not None:
                active_watchlist = None
                print("Watchlist mode exited.")
            continue
        if lower.startswith("watchlist ") or lower.startswith("wl "):
            # Branch-heavy parser for watchlist management grammar and mode switching.
            parts = cmd.split()
            cmd_token = parts[0].lower()
            args = parts[1:]
            if len(args) == 0:
                if cmd_token == "wl":
                    args = ["list"]
                else:
                    if active_watchlist is not None:
                        active_watchlist = None
                        print("Watchlist mode exited.")
                    continue
            sub = args[0].lower()
            if sub == "create":
                if len(args) != 2:
                    print(f"Usage: {cmd_token} create <name>", file=sys.stderr)
                    continue
                rc, msg = _create_watchlist(args[1])
                target = sys.stdout if rc == 0 else sys.stderr
                print(msg, file=target)
                continue
            if sub == "list":
                if len(args) != 1:
                    print(f"Usage: {cmd_token} list", file=sys.stderr)
                    continue
                names = _list_watchlists()
                if not names:
                    print("No watchlists found.")
                    continue
                print("\nWatchlists:")
                for name in names:
                    symbols = _watchlist_symbols(name) or []
                    print(f"- {name} ({len(symbols)} symbols)")
                continue
            if sub == "delete":
                if len(args) != 2:
                    print(f"Usage: {cmd_token} delete <name>", file=sys.stderr)
                    continue
                rc, msg = _delete_watchlist(args[1])
                if rc == 0 and active_watchlist == args[1]:
                    active_watchlist = None
                target = sys.stdout if rc == 0 else sys.stderr
                print(msg, file=target)
                continue
            if sub == "merge":
                if len(args) != 4:
                    print(f"Usage: {cmd_token} merge <wl1> <wl2> <target>", file=sys.stderr)
                    continue
                rc, msg = _merge_watchlists(args[1], args[2], args[3])
                target = sys.stdout if rc == 0 else sys.stderr
                print(msg, file=target)
                continue

            # Canonical entrypoint: `watchlist open <name>`; shorthand `watchlist <name>` remains supported.
            if sub == "open":
                if len(args) != 2:
                    print(f"Usage: {cmd_token} open <name>", file=sys.stderr)
                    continue
                target_name = args[1]
            else:
                if len(args) != 1:
                    print(f"Usage: {cmd_token} <name>", file=sys.stderr)
                    continue
                target_name = args[0]

            if _watchlist_symbols(target_name) is None:
                print(f"Watchlist '{target_name}' not found.", file=sys.stderr)
                continue
            active_watchlist = target_name
            continue
        if lower in {"reload", "r", "refresh"}:
            # Data refresh: always refresh quote, then replay last non-quote view.
            if current_symbol:
                refreshed_info = _get_quote_payload(current_symbol)
                if _has_quote_data(refreshed_info):
                    current_info = refreshed_info
                    _print_quote(current_symbol, current_symbol, include_after_hours=True, preloaded_info=current_info)
                    if last_view_kind == "chart":
                        _draw_chart(
                            current_symbol,
                            period=str(last_view_args.get("period", "6mo")),
                            interval=str(last_view_args.get("interval", "1d")),
                            height=height,
                            width=width,
                            info=current_info,
                            benchmark_override=last_view_args.get("benchmark_override"),
                        )
                    elif last_view_kind == "intraday":
                        _draw_chart(
                            current_symbol,
                            period="1d",
                            interval=str(last_view_args.get("interval", "5m")),
                            height=height,
                            width=width,
                            info=current_info,
                            benchmark_override=last_view_args.get("benchmark_override"),
                        )
                    elif last_view_kind == "table":
                        _render_rebased_table(
                            symbol=current_symbol,
                            info=current_info,
                            benchmark_symbol=last_view_args.get("benchmark_symbol"),
                            benchmark_label=last_view_args.get("benchmark_label"),
                            period_token=str(last_view_args.get("period_token", "6mo")),
                            interval_override=last_view_args.get("interval_override"),
                        )
                    elif last_view_kind == "compare":
                        _render_compare_table(
                            symbol_inputs=list(last_view_args.get("symbols", [])),
                            period_token=str(last_view_args.get("period_token", "6mo")),
                            interval_override=last_view_args.get("interval_override"),
                        )
                else:
                    print(f"Could not refresh quote for '{current_symbol}'.", file=sys.stderr)
            else:
                print("No active symbol. Enter a symbol first.", file=sys.stderr)
            continue
        if lower == "index":
            _print_index_board()
            continue
        if lower == "index list":
            _print_index_catalog()
            continue
        if lower == "code" or lower.startswith("code "):
            _print_code_matches(cmd[4:])
            continue
        if lower == "news" or lower.startswith("news "):
            # Keep grammar strict so accidental bare `news` can be corrected quickly.
            if len(cmd.split(maxsplit=1)) != 2:
                print("Usage: news <code>", file=sys.stderr)
                continue
            _print_symbol_news(cmd.split(maxsplit=1)[1].strip())
            continue
        if lower == "snap":
            if active_watchlist:
                _print_watchlist_snapshot(active_watchlist)
                continue
            if not current_symbol:
                print("No active symbol. Enter an index symbol first.", file=sys.stderr)
                continue
            _print_index_constituent_snap(current_symbol)
            continue
        if lower == "move" or lower.startswith("move ") or lower == "moves" or lower.startswith("moves "):
            parts = cmd.split()
            args = parts[1:] if parts else []
            symbol_inputs, period_token, parse_error = _parse_scope_override_with_period(
                args,
                command_name="moves",
                default_period="1mo",
                period_validator=_is_analytics_period_token,
                period_hint=_ANALYTICS_PERIOD_HINT,
            )
            if parse_error:
                print(parse_error, file=sys.stderr)
                continue
            assert period_token is not None
            _print_moves_snapshot(
                current_symbol=current_symbol,
                active_watchlist=active_watchlist,
                period_token=period_token,
                explicit_symbols=symbol_inputs,
            )
            continue
        if lower == "trend" or lower.startswith("trend ") or lower == "trends" or lower.startswith("trends "):
            parts = cmd.split()
            args = parts[1:] if parts else []
            symbol_inputs, parse_error = _parse_scope_override_no_period(args, command_name="trend")
            if parse_error:
                print(parse_error, file=sys.stderr)
                continue
            _print_trend_snapshot(
                current_symbol=current_symbol,
                active_watchlist=active_watchlist,
                explicit_symbols=symbol_inputs,
            )
            continue
        if lower == "relret" or lower.startswith("relret ") or lower == "rr" or lower.startswith("rr "):
            relret_parts = cmd.split()
            symbol_inputs, period_token, benchmark_input, parse_error = _parse_relret_args(relret_parts[1:])
            if parse_error:
                print(parse_error, file=sys.stderr)
                continue
            assert period_token is not None
            _print_relret_snapshot(
                current_symbol=current_symbol,
                active_watchlist=active_watchlist,
                period_token=period_token,
                explicit_symbols=symbol_inputs,
                benchmark_input=benchmark_input,
            )
            continue
        if lower == "corr" or lower.startswith("corr "):
            symbol_inputs, period_token, parse_error = _parse_scope_override_with_period(
                cmd.split()[1:],
                command_name="corr",
                default_period="1mo",
                period_validator=_is_analytics_period_token,
                period_hint=_ANALYTICS_PERIOD_HINT,
            )
            if parse_error:
                print(parse_error, file=sys.stderr)
                continue
            assert period_token is not None
            _print_corr_snapshot(
                current_symbol=current_symbol,
                active_watchlist=active_watchlist,
                period_token=period_token,
                explicit_symbols=symbol_inputs,
            )
            continue
        if lower in {"list", "ll"} and active_watchlist:
            symbols = _watchlist_symbols(active_watchlist)
            if symbols is None:
                print(f"Watchlist '{active_watchlist}' not found.", file=sys.stderr)
                continue
            if not symbols:
                print(f"\n{active_watchlist} (0 symbols)")
                continue
            print(f"\n{active_watchlist} ({len(symbols)} symbols)")
            for idx, symbol in enumerate(symbols, start=1):
                print(f"{idx:>2}. {symbol}")
            continue
        if lower == "add" or lower.startswith("add "):
            if not active_watchlist:
                print("`add` is available only in watchlist mode.", file=sys.stderr)
                continue
            tokens = cmd.split()[1:]
            if not tokens:
                print("Usage: add <stock code> <stock code> ...", file=sys.stderr)
                continue
            rc, added, rejected, existing_symbols = _add_symbols_to_watchlist(active_watchlist, tokens)
            if rc != 0:
                print(f"Watchlist '{active_watchlist}' not found.", file=sys.stderr)
                continue
            if added:
                print(f"Added to {active_watchlist}: {', '.join(added)}")
            if existing_symbols:
                print(f"Already exists in {active_watchlist}: {', '.join(existing_symbols)}")
            if rejected:
                print(f"Rejected (invalid code): {', '.join(rejected)}", file=sys.stderr)
            if not added and not rejected and not existing_symbols:
                print("No new symbols added.")
            continue
        if lower == "delete" or lower.startswith("delete "):
            if active_watchlist:
                tokens = cmd.split()[1:]
                if not tokens:
                    print("Usage: delete <stock code> <stock code> ...", file=sys.stderr)
                    continue
                rc, removed, missing = _remove_symbols_from_watchlist(active_watchlist, tokens)
                if rc != 0:
                    print(f"Watchlist '{active_watchlist}' not found.", file=sys.stderr)
                    continue
                if removed:
                    print(f"Deleted from {active_watchlist}: {', '.join(removed)}")
                if missing:
                    print(f"Not present in {active_watchlist}: {', '.join(missing)}", file=sys.stderr)
                if not removed and not missing:
                    print("No symbols deleted.")
                continue
        if lower == "cmp" or lower.startswith("cmp "):
            parsed_compare, parse_error = _parse_compare_command_args(cmd.split()[1:])
            if parse_error:
                print(parse_error, file=sys.stderr)
                continue
            assert parsed_compare is not None
            _render_compare_table(
                symbol_inputs=list(parsed_compare.symbols),
                period_token=parsed_compare.period_token,
                interval_override=parsed_compare.interval_override,
            )
            last_view_kind = "compare"
            last_view_args = {
                "symbols": list(parsed_compare.symbols),
                "period_token": parsed_compare.period_token,
                "interval_override": parsed_compare.interval_override,
            }
            continue

        if lower == "table" or lower.startswith("table "):
            parts = cmd.split()
            if len(parts) < 2:
                print("Usage: table <swing|intra> ...", file=sys.stderr)
                continue
            mode = parts[1].lower()
            # Canonical router keeps legacy alias implementation as the single execution path.
            if mode not in {"swing", "intra"}:
                print("Usage: table <swing|intra> ...", file=sys.stderr)
                continue
            alias = "t" if mode == "swing" else "tt"
            tail = " ".join(parts[2:])
            cmd = f"{alias} {tail}".strip()
            lower = cmd.lower()

        if lower == "tt" or lower.startswith("tt "):
            if not current_symbol:
                print("No active symbol. Enter a symbol first.", file=sys.stderr)
                continue

            args = cmd.split()[1:]
            period_token: str
            interval_override: str | None
            benchmark_input: str | None

            if len(args) == 0:
                # Default tt mode mirrors cc defaults but renders table-only output.
                parsed_intraday, parse_error = _parse_intraday_command_args(args)
                if parse_error:
                    print(parse_error, file=sys.stderr)
                    continue
                assert parsed_intraday is not None
                period_token = "1d"
                interval_override = parsed_intraday.interval
                benchmark_input = parsed_intraday.benchmark_input
            elif args[0] == "-" or (len(args) >= 2 and args[1] == "-"):
                # Explicit preserved-structure syntax always goes through swing parser.
                parsed_swing, parse_error = _parse_swing_command_args(args, command_name="tt")
                if parse_error:
                    print(parse_error, file=sys.stderr)
                    continue
                assert parsed_swing is not None
                period_token = parsed_swing.period_token
                interval_override = parsed_swing.interval_override
                benchmark_input = parsed_swing.benchmark_input
            elif len(args) == 1:
                # tt is intraday-first: one token means interval or benchmark symbol.
                parsed_intraday, parse_error = _parse_intraday_command_args(args)
                if parse_error:
                    print(parse_error, file=sys.stderr)
                    continue
                assert parsed_intraday is not None
                period_token = "1d"
                interval_override = parsed_intraday.interval
                benchmark_input = parsed_intraday.benchmark_input
            elif len(args) == 2:
                # Two-token tt form is intraday benchmark + minute interval.
                parsed_intraday, parse_error = _parse_intraday_command_args(args)
                if parse_error:
                    print(
                        "Usage: tt | tt <1m|5m|15m|30m|1hr> | tt <code> | tt <code> <1m|5m|15m|30m|1hr> "
                        "| tt - <period> [agg] | tt <code> - <period> [agg]",
                        file=sys.stderr,
                    )
                    continue
                assert parsed_intraday is not None
                period_token = "1d"
                interval_override = parsed_intraday.interval
                benchmark_input = parsed_intraday.benchmark_input
            else:
                print(
                    "Usage: tt | tt <1m|5m|15m|30m|1hr> | tt <code> | tt <code> <1m|5m|15m|30m|1hr> "
                    "| tt - <period> [agg] | tt <code> - <period> [agg]",
                    file=sys.stderr,
                )
                continue

            bench_symbol, bench_label, bench_error = _resolve_benchmark_for_table(
                active_symbol=current_symbol,
                active_info=current_info,
                benchmark_input=benchmark_input,
            )
            if bench_error:
                print(bench_error, file=sys.stderr)
                continue

            _render_rebased_table(
                symbol=current_symbol,
                info=current_info,
                benchmark_symbol=bench_symbol,
                benchmark_label=bench_label,
                period_token=period_token,
                interval_override=interval_override,
            )
            last_view_kind = "table"
            last_view_args = {
                "benchmark_symbol": bench_symbol,
                "benchmark_label": bench_label,
                "period_token": period_token,
                "interval_override": interval_override,
            }
            continue

        if lower == "t" or lower.startswith("t "):
            if not current_symbol:
                print("No active symbol. Enter a symbol first.", file=sys.stderr)
                continue
            # Table mode: parse grammar first, then resolve benchmark symbol.
            parsed, parse_error = _parse_swing_command_args(cmd.split()[1:], command_name="t")
            if parse_error:
                print(parse_error, file=sys.stderr)
                continue
            assert parsed is not None

            bench_symbol, bench_label, bench_error = _resolve_benchmark_for_table(
                active_symbol=current_symbol,
                active_info=current_info,
                benchmark_input=parsed.benchmark_input,
            )
            if bench_error:
                print(bench_error, file=sys.stderr)
                continue

            _render_rebased_table(
                symbol=current_symbol,
                info=current_info,
                benchmark_symbol=bench_symbol,
                benchmark_label=bench_label,
                period_token=parsed.period_token,
                interval_override=parsed.interval_override,
            )
            last_view_kind = "table"
            last_view_args = {
                "benchmark_symbol": bench_symbol,
                "benchmark_label": bench_label,
                "period_token": parsed.period_token,
                "interval_override": parsed.interval_override,
            }
            continue

        if lower == "chart" or lower.startswith("chart "):
            parts = cmd.split()
            if len(parts) < 2:
                print("Usage: chart <swing|intra> ...", file=sys.stderr)
                continue
            mode = parts[1].lower()
            # Canonical router keeps legacy alias implementation as the single execution path.
            if mode not in {"swing", "intra"}:
                print("Usage: chart <swing|intra> ...", file=sys.stderr)
                continue
            alias = "c" if mode == "swing" else "cc"
            tail = " ".join(parts[2:])
            cmd = f"{alias} {tail}".strip()
            lower = cmd.lower()

        if lower == "cc" or lower.startswith("cc "):
            if not current_symbol:
                print("No active symbol. Enter a symbol first.", file=sys.stderr)
                continue

            # Intraday mode is restricted to minute intervals and optional benchmark override.
            parsed, parse_error = _parse_intraday_command_args(cmd.split()[1:])
            if parse_error:
                print(parse_error, file=sys.stderr)
                continue
            assert parsed is not None

            bench_override, bench_error = _resolve_benchmark_override(parsed.benchmark_input)
            if bench_error:
                print(bench_error, file=sys.stderr)
                continue

            _draw_chart(
                current_symbol,
                period="1d",
                interval=parsed.interval,
                height=height,
                width=width,
                info=current_info,
                benchmark_override=bench_override,
            )
            last_view_kind = "intraday"
            last_view_args = {"interval": parsed.interval, "benchmark_override": bench_override}
            continue

        if lower == "c" or lower.startswith("c "):
            if not current_symbol:
                print("No active symbol. Enter a symbol first.", file=sys.stderr)
                continue

            # Swing chart mode shares grammar with table mode for consistency.
            parsed, parse_error = _parse_swing_command_args(cmd.split()[1:], command_name="c")
            if parse_error:
                print(parse_error, file=sys.stderr)
                continue
            assert parsed is not None

            bench_override, bench_error = _resolve_benchmark_override(parsed.benchmark_input)
            if bench_error:
                print(bench_error, file=sys.stderr)
                continue

            _draw_chart(
                current_symbol,
                period=parsed.period_token,
                interval=parsed.interval_override or _interval_for_chart_period(parsed.period_token),
                height=height,
                width=width,
                info=current_info,
                benchmark_override=bench_override,
            )
            last_view_kind = "chart"
            last_view_args = {
                "period": parsed.period_token,
                "interval": parsed.interval_override or _interval_for_chart_period(parsed.period_token),
                "benchmark_override": bench_override,
            }
            continue

        shortcut_period = _normalize_period_token(lower)
        if shortcut_period is not None:
            if not current_symbol:
                print("No active symbol. Enter a symbol first.", file=sys.stderr)
                continue
            # Bare period token is a convenience shortcut for swing chart.
            interval = _interval_for_chart_period(shortcut_period)
            _draw_chart(
                current_symbol,
                period=shortcut_period,
                interval=interval,
                height=height,
                width=width,
                info=current_info,
            )
            last_view_kind = "chart"
            last_view_args = {"period": shortcut_period, "interval": interval, "benchmark_override": None}
            continue

        # Any other input is treated as a symbol switch.
        # In index mode, keep index nicknames/index aliases in index space and skip equity fuzzy fallback.
        if current_symbol and _is_known_index_symbol(current_symbol):
            index_target = _index_alias_target(cmd)
            if index_target is not None:
                resolved_symbol, preloaded_info = _resolve_symbol(index_target)
                current_symbol = resolved_symbol
                # Index tickers can have sparse/empty `Ticker` payloads; backfill from grouped snapshot path.
                if preloaded_info is None:
                    preloaded_info = _index_quote_fallback_payload(current_symbol)
                current_info = preloaded_info
                # Symbol switch from watchlist mode returns control to symbol-mode prompt.
                active_watchlist = None
                if preloaded_info is not None:
                    _print_quote(cmd.strip().upper(), current_symbol, include_after_hours=True, preloaded_info=current_info)
                else:
                    print(f"Switched to index '{current_symbol}' (quote unavailable right now).", file=sys.stderr)
                last_view_kind = "quote"
                last_view_args = {}
                continue

        resolved_symbol, preloaded_info = _resolve_symbol_with_fallback(cmd)
        if active_watchlist is not None:
            mode_return_target = ("watchlist", active_watchlist, None)
        elif current_symbol and _is_index_context_symbol(current_symbol) and not _is_index_context_symbol(resolved_symbol):
            mode_return_target = ("index", _normalize_snap_index_symbol(current_symbol), current_info)
        # Keep index quote behavior consistent outside index-mode alias branch.
        if preloaded_info is None and _is_known_index_symbol(resolved_symbol):
            preloaded_info = _index_quote_fallback_payload(resolved_symbol)
        if preloaded_info is None:
            # Key control-flow choice: preserve index context switch even when quote data is unavailable.
            if _is_known_index_symbol(resolved_symbol):
                current_symbol = resolved_symbol
                current_info = None
                active_watchlist = None
                print(f"Switched to index '{current_symbol}' (quote unavailable right now).", file=sys.stderr)
                last_view_kind = "quote"
                last_view_args = {}
                continue
            print(f"Could not fetch quote for '{cmd}'.", file=sys.stderr)
            continue
        current_symbol = resolved_symbol
        current_info = preloaded_info
        # Symbol switch from watchlist mode returns control to symbol-mode prompt.
        active_watchlist = None
        _print_quote(cmd.strip().upper(), current_symbol, include_after_hours=True, preloaded_info=current_info)
        last_view_kind = "quote"
        last_view_args = {}


def main(argv: list[str] | None = None) -> int:
    """Program entry point for one-shot mode or interactive REPL."""
    raw_argv = sys.argv[1:] if argv is None else argv
    if len(raw_argv) == 0:
        return _run_repl(
            start_input_symbol=None,
            start_resolved_symbol=None,
            start_info=None,
            width=100,
            height=22,
        )

    _reset_network_call_metrics()
    parser = _build_parser()
    should_print_footer = True
    try:
        args = parser.parse_args(raw_argv)
        resolved_symbol, preloaded_info = _resolve_symbol_with_fallback(args.symbol)
        # Non-REPL entry should still render indices when quote payload is sparse.
        if preloaded_info is None and _is_known_index_symbol(resolved_symbol):
            preloaded_info = _index_quote_fallback_payload(resolved_symbol)

        if args.command == "quote":
            return _print_quote(
                args.symbol,
                resolved_symbol,
                include_after_hours=not args.no_after_hours,
                preloaded_info=preloaded_info,
            )

        if args.command == "chart":
            return _draw_chart(
                resolved_symbol,
                period=args.period,
                interval=args.interval,
                height=args.height,
                width=args.width,
                info=preloaded_info,
            )

        should_print_footer = False
        return _run_repl(
            start_input_symbol=args.symbol.strip().upper(),
            start_resolved_symbol=resolved_symbol,
            start_info=preloaded_info,
            width=args.width,
            height=args.height,
        )
    finally:
        if should_print_footer:
            _print_network_call_metrics()


if __name__ == "__main__":
    raise SystemExit(main())
