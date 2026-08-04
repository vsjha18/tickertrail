"""Pure, network-free parsers for interactive command grammar."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from . import timeframe


ANALYTICS_PERIOD_HINT = "Nd|Nmo(<12)|Ny"
INTRADAY_INTERVAL_ALIASES: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "1hr": "1h",
}


@dataclass(frozen=True)
class SwingCommand:
    """Parsed form of a swing table or chart command."""

    period_token: str = "6mo"
    interval_override: str | None = None
    benchmark_input: str | None = None


@dataclass(frozen=True)
class IntradayCommand:
    """Parsed form of an intraday table or chart command."""

    interval: str = "5m"
    benchmark_input: str | None = None


@dataclass(frozen=True)
class CompareCommand:
    """Parsed form of a multi-instrument comparison command."""

    symbols: tuple[str, ...]
    period_token: str = "6mo"
    interval_override: str | None = None


def parse_swing_command_args(args: list[str], command_name: str) -> tuple[SwingCommand | None, str | None]:
    """Parse swing command arguments into a typed command specification."""
    usage = (
        f"Usage: {command_name} | {command_name} <benchmark> [period [agg]] | "
        f"{command_name} - <period|agg> [agg] | {command_name} <benchmark> - <period|agg> [agg]"
    )
    if len(args) == 0:
        return SwingCommand(), None

    # Dash grammar can override period, aggregation, or both without replacing context.
    if args[0] == "-":
        if len(args) not in {2, 3}:
            return None, f"Usage: {command_name} - <period|agg> [agg]"
        period_token = timeframe.normalize_period_token(args[1])
        interval_override = timeframe.normalize_agg_token(args[1])
        if len(args) == 2:
            if period_token is not None:
                return SwingCommand(period_token=period_token), None
            if interval_override is not None:
                return SwingCommand(interval_override=interval_override), None
            return None, f"Unsupported period/aggregation token '{args[1]}'."
        if period_token is None:
            return None, f"Unsupported period token '{args[1]}'."
        tail_interval = timeframe.normalize_agg_token(args[2])
        if tail_interval is None:
            return None, f"Unsupported aggregation token '{args[2]}'."
        return SwingCommand(period_token=period_token, interval_override=tail_interval), None

    if len(args) >= 2 and args[1] == "-":
        if len(args) not in {3, 4}:
            return None, f"Usage: {command_name} <benchmark> - <period|agg> [agg]"
        period_token = timeframe.normalize_period_token(args[2])
        interval_override = timeframe.normalize_agg_token(args[2])
        if len(args) == 3:
            if period_token is not None:
                return SwingCommand(period_token=period_token, benchmark_input=args[0]), None
            if interval_override is not None:
                return SwingCommand(interval_override=interval_override, benchmark_input=args[0]), None
            return None, f"Unsupported period/aggregation token '{args[2]}'."
        if period_token is None:
            return None, f"Unsupported period token '{args[2]}'."
        interval_override = timeframe.normalize_agg_token(args[3])
        if interval_override is None:
            return None, f"Unsupported aggregation token '{args[3]}'."
        return SwingCommand(period_token, interval_override, args[0]), None

    if len(args) == 1:
        period_token = timeframe.normalize_period_token(args[0])
        if period_token is not None:
            return SwingCommand(period_token=period_token), None
        return SwingCommand(benchmark_input=args[0]), None

    if len(args) == 2:
        period_token = timeframe.normalize_period_token(args[0])
        interval_override = timeframe.normalize_agg_token(args[1])
        if period_token is not None and interval_override is not None:
            return SwingCommand(period_token, interval_override), None
        period_token = timeframe.normalize_period_token(args[1])
        if period_token is None:
            return None, usage
        return SwingCommand(period_token=period_token, benchmark_input=args[0]), None

    if len(args) == 3:
        period_token = timeframe.normalize_period_token(args[1])
        interval_override = timeframe.normalize_agg_token(args[2])
        if period_token is None or interval_override is None:
            return None, f"Usage: {command_name} <benchmark> <period> [agg]"
        return SwingCommand(period_token, interval_override, args[0]), None
    return None, usage


def parse_intraday_command_args(args: list[str], command_name: str = "cc") -> tuple[IntradayCommand | None, str | None]:
    """Parse intraday command arguments into a typed command specification."""
    usage = (
        f"Usage: {command_name} | {command_name} <1m|5m|15m|30m|1hr> | "
        f"{command_name} <benchmark> | {command_name} <benchmark> <1m|5m|15m|30m|1hr> | "
        f"{command_name} - <1m|5m|15m|30m|1hr> | {command_name} <benchmark> - <1m|5m|15m|30m|1hr>"
    )
    if len(args) == 0:
        return IntradayCommand(), None
    if args[0] == "-":
        if len(args) != 2:
            return None, usage
        interval = INTRADAY_INTERVAL_ALIASES.get(args[1].strip().lower())
        return (IntradayCommand(interval=interval), None) if interval is not None else (None, usage)
    if len(args) >= 2 and args[1] == "-":
        if len(args) != 3:
            return None, usage
        interval = INTRADAY_INTERVAL_ALIASES.get(args[2].strip().lower())
        return (IntradayCommand(interval, args[0]), None) if interval is not None else (None, usage)
    if len(args) == 1:
        interval = INTRADAY_INTERVAL_ALIASES.get(args[0].strip().lower())
        if interval is not None:
            return IntradayCommand(interval=interval), None
        return IntradayCommand(benchmark_input=args[0]), None
    if len(args) == 2:
        interval = INTRADAY_INTERVAL_ALIASES.get(args[1].strip().lower())
        return (IntradayCommand(interval, args[0]), None) if interval is not None else (None, usage)
    return None, usage


def normalize_compare_period_token(period_token: str) -> str | None:
    """Normalize compare periods, including month shorthand such as `6m`."""
    normalized = timeframe.normalize_period_token(period_token)
    if normalized is not None:
        return normalized
    match = re.fullmatch(r"(\d+)m", period_token.strip().lower())
    return timeframe.normalize_period_token(f"{match.group(1)}mo") if match else None


def parse_compare_command_args(args: list[str]) -> tuple[CompareCommand | None, str | None]:
    """Parse comparison arguments as symbols followed by optional period and aggregation."""
    usage = "Usage: cmp <symbol1> <symbol2> [symbolN ...] [period [agg]]"
    cleaned = [token.strip() for token in args if token.strip()]
    if len(cleaned) < 2 or "--" in cleaned:
        return None, usage
    period_token = "6mo"
    interval_override = None
    symbols_end = len(cleaned)

    # Prefer a valid `[period, aggregation]` tail over treating those tokens as symbols.
    if len(cleaned) >= 4:
        maybe_interval = timeframe.normalize_agg_token(cleaned[-1])
        maybe_period = normalize_compare_period_token(cleaned[-2])
        if maybe_interval is not None:
            if maybe_period is None:
                return None, f"Unsupported period token '{cleaned[-2]}'."
            interval_override = maybe_interval
            period_token = maybe_period
            symbols_end -= 2
    if symbols_end == len(cleaned):
        maybe_interval = timeframe.normalize_agg_token(cleaned[-1])
        maybe_period = normalize_compare_period_token(cleaned[-1])
        if maybe_interval is not None and maybe_period is None:
            return None, usage
        if maybe_period is not None and len(cleaned) >= 3:
            period_token = maybe_period
            symbols_end -= 1

    symbols = tuple(dict.fromkeys(symbol for symbol in cleaned[:symbols_end] if symbol))
    if len(symbols) < 2:
        return None, "Provide at least two distinct symbols for `cmp`."
    return CompareCommand(symbols, period_token, interval_override), None


def is_analytics_period_token(token: str | None) -> bool:
    """Return whether a token matches the supported analytics period grammar."""
    if token is None:
        return False
    match = re.fullmatch(r"(\d+)(d|mo|y)", token)
    if not match:
        return False
    count = int(match.group(1))
    return count > 0 and (match.group(2) != "mo" or count < 12)


def parse_moves_period(args: list[str], period_hint: str = ANALYTICS_PERIOD_HINT) -> tuple[str | None, str | None]:
    """Parse the legacy move-period-only grammar."""
    if len(args) > 1:
        return None, f"Usage: moves [{period_hint}]"
    if not args:
        return "1mo", None
    token = timeframe.normalize_period_token(args[0])
    return (token, None) if is_analytics_period_token(token) else (None, f"Usage: moves [{period_hint}]")


def parse_scope_override_with_period(
    args: list[str],
    *,
    command_name: str,
    period_tokens: set[str] | None = None,
    default_period: str,
    period_validator: Callable[[str | None], bool] | None = None,
    period_hint: str | None = None,
) -> tuple[list[str] | None, str | None, str | None]:
    """Parse optional `on <codes...> [period]` analytics grammar."""
    if period_validator is None:
        token_set = period_tokens or set()
        period_validator = lambda token: token in token_set if token is not None else False
    if period_hint is None:
        period_hint = (
            "|".join(sorted(period_tokens, key=lambda token: (timeframe.period_token_days(token) or 0, token)))
            if period_tokens
            else "period"
        )
    usage = f"Usage: {command_name} [{period_hint}] | {command_name} on <code1> <code2> ... [{period_hint}]"
    cleaned = [token.strip() for token in args if token.strip()]
    if not cleaned:
        return None, default_period, None
    if cleaned[0].lower() != "on":
        if len(cleaned) != 1:
            return None, None, usage
        token = timeframe.normalize_period_token(cleaned[0])
        return (None, token, None) if period_validator(token) else (None, None, usage)
    if len(cleaned) < 2:
        return None, None, usage

    # A valid trailing period belongs to the grammar; all preceding tokens are symbols.
    symbol_inputs = cleaned[1:]
    period_token = default_period
    if len(symbol_inputs) > 1:
        maybe_period = timeframe.normalize_period_token(symbol_inputs[-1])
        if period_validator(maybe_period):
            period_token = maybe_period
            symbol_inputs = symbol_inputs[:-1]
        elif maybe_period is not None:
            return None, None, usage
    return (symbol_inputs, period_token, None) if symbol_inputs else (None, None, usage)


def parse_scope_override_no_period(args: list[str], *, command_name: str) -> tuple[list[str] | None, str | None]:
    """Parse optional `on <codes...>` grammar for commands without a period."""
    usage = f"Usage: {command_name} | {command_name} on <code1> <code2> ..."
    cleaned = [token.strip() for token in args if token.strip()]
    if not cleaned:
        return None, None
    if cleaned[0].lower() != "on" or len(cleaned) < 2:
        return None, usage
    return cleaned[1:], None


def parse_relret_args(args: list[str], period_hint: str = ANALYTICS_PERIOD_HINT) -> tuple[list[str] | None, str | None, str | None, str | None]:
    """Parse relative-return symbols, period, and optional benchmark override."""
    usage = (
        f"Usage: relret [{period_hint}] [vs <benchmark>] | "
        f"relret on <code1> <code2> ... [{period_hint}] [vs <benchmark>]"
    )
    cleaned = [token.strip() for token in args if token.strip()]
    if not cleaned:
        return None, "1mo", None, None

    benchmark_input: str | None = None
    period_after_vs: str | None = None
    head_tokens = cleaned
    if "vs" in (token.lower() for token in cleaned):
        # Permit exactly one benchmark marker and one optional period after it.
        positions = [index for index, token in enumerate(cleaned) if token.lower() == "vs"]
        if len(positions) != 1:
            return None, None, None, usage
        vs_index = positions[0]
        tail = cleaned[vs_index + 1 :]
        if len(tail) not in {1, 2}:
            return None, None, None, usage
        benchmark_input = tail[0]
        if len(tail) == 2:
            period_after_vs = timeframe.normalize_period_token(tail[1])
            if not is_analytics_period_token(period_after_vs):
                return None, None, None, usage
        head_tokens = cleaned[:vs_index]

    if not head_tokens:
        return None, period_after_vs or "1mo", benchmark_input, None
    if head_tokens[0].lower() == "on":
        if len(head_tokens) < 2:
            return None, None, None, usage
        symbols = head_tokens[1:]
        period_token = period_after_vs or "1mo"
        if len(symbols) > 1:
            maybe_period = timeframe.normalize_period_token(symbols[-1])
            if is_analytics_period_token(maybe_period):
                if period_after_vs is not None:
                    return None, None, None, usage
                period_token = maybe_period
                symbols = symbols[:-1]
            elif maybe_period is not None:
                return None, None, None, usage
        return (symbols, period_token, benchmark_input, None) if symbols else (None, None, None, usage)
    if len(head_tokens) > 1:
        return None, None, None, usage
    token = timeframe.normalize_period_token(head_tokens[0])
    if not is_analytics_period_token(token) or period_after_vs is not None:
        return None, None, None, usage
    return None, token, benchmark_input, None


def parse_corr_period(args: list[str], period_hint: str = ANALYTICS_PERIOD_HINT) -> tuple[str | None, str | None]:
    """Parse the legacy correlation period-only grammar."""
    if len(args) > 1:
        return None, f"Usage: corr [{period_hint}]"
    if not args:
        return "1mo", None
    token = timeframe.normalize_period_token(args[0])
    return (token, None) if is_analytics_period_token(token) else (None, f"Usage: corr [{period_hint}]")
