from __future__ import annotations

import datetime as dt
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


NIFTY_INSTRUMENT_KEY = "NSE_INDEX|Nifty 50"
TOKEN_FILE = Path(__file__).resolve().parents[2] / ".upstox_analytics_token"
USER_AGENT = "TickerTrail/0.1 (+https://github.com/vsjha18/tickertrail)"
EXPIRY_QUALIFIERS = {
    "near": "near",
    "next": "next",
    "far": "far",
    "month": "month",
}
CHAIN_USAGE = "chain [near|next|far|month|expiry YYYY-MM-DD] [strikes <1-25>]"
OPTION_DETAIL_USAGE = "opt <strike> [near|next|far|month|expiry YYYY-MM-DD]"


class UpstoxError(RuntimeError):
    """Describe a safe, user-facing Upstox configuration or API failure."""


@dataclass(frozen=True)
class ChainRequest:
    """Describe one normalized option-chain request."""

    qualifier: str
    expiry_value: str
    strikes_each_side: int = 10


@dataclass(frozen=True)
class OptionDetailRequest:
    """Describe one normalized option strike-detail request."""

    strike: float
    qualifier: str
    expiry_value: str


@dataclass(frozen=True)
class OptionSide:
    """Hold market data and Greeks for one call or put contract."""

    ltp: float | None
    close_price: float | None
    volume: float | None
    oi: float | None
    iv: float | None
    delta: float | None
    gamma: float | None
    theta: float | None
    vega: float | None
    instrument_key: str | None = None
    bid_price: float | None = None
    bid_qty: float | None = None
    ask_price: float | None = None
    ask_qty: float | None = None
    prev_oi: float | None = None
    pop: float | None = None


@dataclass(frozen=True)
class OptionChainRow:
    """Hold both option sides for one strike in an expiry chain."""

    strike: float
    expiry: str
    spot: float | None
    call: OptionSide
    put: OptionSide


@dataclass(frozen=True)
class OptionUnderlying:
    """Identify one Upstox stock or index that may have option contracts."""

    instrument_key: str
    trading_symbol: str
    display_name: str
    segment: str


@dataclass(frozen=True)
class UnderlyingQuote:
    """Hold an option underlying's current value and previous session close."""

    last_price: float | None
    close_price: float | None


@dataclass(frozen=True)
class FullMarketQuote:
    """Hold one instrument's latest price and current-session range."""

    instrument_key: str
    last_price: float | None
    close_price: float | None
    open_price: float | None
    day_high: float | None
    day_low: float | None
    timestamp: str | None


# Retain the original public name for callers created with the NIFTY-only feature.
NiftyQuote = UnderlyingQuote


@dataclass(frozen=True)
class OptionExpiry:
    """Describe one available option expiry, classification, and lot size."""

    expiry: str
    weekly: bool
    lot_size: int | None = None


JsonRequest = Callable[[str, dict[str, str], str], dict[str, Any]]


def token_file_path() -> Path:
    """Return the canonical repository-local Upstox token path."""
    return TOKEN_FILE


def save_analytics_token(token: str) -> Path:
    """Atomically persist a non-empty Upstox analytics token."""
    cleaned = token.strip()
    if not cleaned:
        raise UpstoxError("Upstox token cannot be empty.")
    path = token_file_path()
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(f"{cleaned}\n", encoding="utf-8")
        os.chmod(tmp_path, 0o600)
        tmp_path.replace(path)
    except OSError as exc:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise UpstoxError(f"Could not save Upstox token to {path}.") from exc
    return path


def load_analytics_token() -> str:
    """Load the configured Upstox token or raise a useful configuration error."""
    path = token_file_path()
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise UpstoxError(
            "Upstox token is not configured. Use `config`, then "
            "`token add upstox <token>`, then `end`."
        ) from exc
    if not token:
        raise UpstoxError(f"Upstox token file is empty: {path}")
    return token


def token_is_configured() -> bool:
    """Return whether the canonical token file contains a token."""
    try:
        return bool(load_analytics_token())
    except UpstoxError:
        return False


def parse_chain_args(args: list[str]) -> tuple[ChainRequest | None, str | None]:
    """Parse expiry and strike-count modifiers for an option-chain command."""
    tokens = [token.strip() for token in args if token.strip()]
    qualifier = "near"
    expiry_value = EXPIRY_QUALIFIERS[qualifier]

    # The first modifier selects exactly one relative or explicit expiry.
    if tokens and tokens[0].lower() in EXPIRY_QUALIFIERS:
        qualifier = tokens.pop(0).lower()
        expiry_value = EXPIRY_QUALIFIERS[qualifier]
    elif tokens and tokens[0].lower() == "expiry":
        if len(tokens) < 2:
            return None, f"Incomplete command. Usage: {CHAIN_USAGE}"
        raw_date = tokens[1]
        try:
            dt.date.fromisoformat(raw_date)
        except ValueError:
            return None, f"Invalid expiry date '{raw_date}'. Use YYYY-MM-DD."
        qualifier = "expiry"
        expiry_value = raw_date
        tokens = tokens[2:]

    strikes_each_side = 10
    if tokens:
        if len(tokens) != 2 or tokens[0].lower() != "strikes":
            return None, f"Usage: {CHAIN_USAGE}"
        try:
            strikes_each_side = int(tokens[1])
        except ValueError:
            return None, "Strike count must be a whole number from 1 to 25."
        if not 1 <= strikes_each_side <= 25:
            return None, "Strike count must be from 1 to 25."

    return ChainRequest(qualifier, expiry_value, strikes_each_side), None


def parse_option_detail_args(
    args: list[str],
) -> tuple[OptionDetailRequest | None, str | None]:
    """Parse a strike followed by one optional option-expiry selector."""
    tokens = [token.strip() for token in args if token.strip()]
    if not tokens:
        return None, f"Incomplete command. Usage: {OPTION_DETAIL_USAGE}"

    raw_strike = tokens.pop(0).replace(",", "")
    try:
        strike = float(raw_strike)
    except ValueError:
        return None, "Strike must be a positive number, for example 24200 or 1,400.50."
    if not math.isfinite(strike) or strike <= 0:
        return None, "Strike must be a positive number, for example 24200 or 1,400.50."

    qualifier = "near"
    expiry_value = EXPIRY_QUALIFIERS[qualifier]

    # Detail commands accept exactly one expiry selector and never a strike-window modifier.
    if tokens and tokens[0].lower() in EXPIRY_QUALIFIERS:
        if len(tokens) != 1:
            return None, f"Usage: {OPTION_DETAIL_USAGE}"
        qualifier = tokens[0].lower()
        expiry_value = EXPIRY_QUALIFIERS[qualifier]
    elif tokens and tokens[0].lower() == "expiry":
        if len(tokens) < 2:
            return None, f"Incomplete command. Usage: {OPTION_DETAIL_USAGE}"
        if len(tokens) != 2:
            return None, f"Usage: {OPTION_DETAIL_USAGE}"
        raw_date = tokens[1]
        try:
            dt.date.fromisoformat(raw_date)
        except ValueError:
            return None, f"Invalid expiry date '{raw_date}'. Use YYYY-MM-DD."
        qualifier = "expiry"
        expiry_value = raw_date
    elif tokens:
        return None, f"Usage: {OPTION_DETAIL_USAGE}"

    return OptionDetailRequest(strike, qualifier, expiry_value), None


def _float_or_none(value: Any) -> float | None:
    """Convert one API scalar to float without propagating malformed data."""
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _positive_int_or_none(value: Any) -> int | None:
    """Convert a positive whole-number API scalar to int when possible."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not parsed.is_integer() or parsed <= 0:
        return None
    return int(parsed)


def _api_error_message(payload: Any, status_code: int) -> str:
    """Extract a safe message from one Upstox error payload."""
    if isinstance(payload, dict):
        # Cloudflare failures happen before Upstox authentication and must not be called token failures.
        if payload.get("cloudflare_error"):
            detail = str(payload.get("detail") or payload.get("title") or "Access denied").strip()
            error_code = str(payload.get("error_code") or "").strip()
            suffix = f" ({error_code})" if error_code else ""
            return f"Upstox gateway blocked the request{suffix}: {detail}"
        errors = payload.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            message = str(errors[0].get("message") or "").strip()
            if message:
                return message
        message = str(payload.get("message") or "").strip()
        if message:
            return message
    if status_code == 401:
        return "Upstox rejected the configured analytics token."
    if status_code == 403:
        return "Upstox denied access to this request (HTTP 403)."
    return f"Upstox request failed with HTTP {status_code}."


def request_json(endpoint: str, params: dict[str, str], token: str) -> dict[str, Any]:
    """Perform one authenticated Upstox GET request and decode its JSON body."""
    url = f"https://api.upstox.com{endpoint}?{urlencode(params)}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = None
        raise UpstoxError(_api_error_message(payload, exc.code)) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise UpstoxError("Could not reach Upstox. Check the network and try again.") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise UpstoxError("Upstox returned an unreadable response.") from exc
    if not isinstance(payload, dict):
        raise UpstoxError("Upstox returned an unexpected response.")
    return payload


def _parse_option_side(payload: Any) -> OptionSide:
    """Normalize one call or put block from an option-chain response."""
    option = payload if isinstance(payload, dict) else {}
    market = option.get("market_data") if isinstance(option.get("market_data"), dict) else {}
    greeks = option.get("option_greeks") if isinstance(option.get("option_greeks"), dict) else {}
    return OptionSide(
        ltp=_float_or_none(market.get("ltp")),
        close_price=_float_or_none(market.get("close_price")),
        volume=_float_or_none(market.get("volume")),
        oi=_float_or_none(market.get("oi")),
        iv=_float_or_none(greeks.get("iv")),
        delta=_float_or_none(greeks.get("delta")),
        gamma=_float_or_none(greeks.get("gamma")),
        theta=_float_or_none(greeks.get("theta")),
        vega=_float_or_none(greeks.get("vega")),
        instrument_key=str(option.get("instrument_key") or "").strip() or None,
        bid_price=_float_or_none(market.get("bid_price")),
        bid_qty=_float_or_none(market.get("bid_qty")),
        ask_price=_float_or_none(market.get("ask_price")),
        ask_qty=_float_or_none(market.get("ask_qty")),
        prev_oi=_float_or_none(market.get("prev_oi")),
        pop=_float_or_none(greeks.get("pop")),
    )


def _instrument_identity(value: Any) -> str:
    """Normalize an instrument label for strict case-insensitive matching."""
    return "".join(character for character in str(value or "").upper() if character.isalnum())


def resolve_option_underlying(
    token: str,
    query: str,
    request_json_fn: JsonRequest | None = None,
    preferred_exchange: str = "NSE",
) -> OptionUnderlying:
    """Resolve an exact Indian stock or index query to its Upstox instrument key."""
    cleaned_query = " ".join(query.strip().split())
    identity = _instrument_identity(cleaned_query)
    if not identity:
        raise UpstoxError("Enter a stock ticker or index name for the option chain.")
    fetch = request_json_fn or request_json
    payload = fetch(
        "/v2/instruments/search",
        {
            "query": cleaned_query,
            "exchanges": "NSE,BSE",
            "segments": "EQ,INDEX",
            "page_number": "1",
            "records": "30",
        },
        token,
    )
    raw_rows = payload.get("data")
    if not isinstance(raw_rows, list):
        raise UpstoxError(f"Upstox could not resolve stock or index '{cleaned_query}'.")

    # Require an exact ticker/name identity so a fuzzy search cannot select another security.
    ranked: list[tuple[tuple[int, int], dict[str, Any]]] = []
    exchange_order = (preferred_exchange.strip().upper(), "NSE", "BSE")
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            continue
        segment = str(raw_row.get("segment") or "").strip().upper()
        instrument_key = str(raw_row.get("instrument_key") or "").strip()
        if segment not in {"NSE_EQ", "BSE_EQ", "NSE_INDEX", "BSE_INDEX"} or not instrument_key:
            continue
        fields = (
            raw_row.get("trading_symbol"),
            raw_row.get("name"),
            raw_row.get("short_name"),
        )
        exact_field = next(
            (index for index, value in enumerate(fields) if _instrument_identity(value) == identity),
            None,
        )
        if exact_field is None:
            continue
        exchange = str(raw_row.get("exchange") or segment.split("_", 1)[0]).strip().upper()
        try:
            exchange_rank = exchange_order.index(exchange)
        except ValueError:
            exchange_rank = len(exchange_order)
        ranked.append(((exact_field, exchange_rank), raw_row))
    if not ranked:
        raise UpstoxError(
            f"Upstox could not exactly match stock or index '{cleaned_query}'. "
            "Use its exchange ticker or a supported index alias."
        )

    selected = min(ranked, key=lambda item: item[0])[1]
    segment = str(selected.get("segment") or "").strip().upper()
    trading_symbol = str(selected.get("trading_symbol") or cleaned_query).strip()
    name = str(selected.get("name") or trading_symbol).strip()
    display_name = name if segment.endswith("_INDEX") else trading_symbol
    return OptionUnderlying(
        instrument_key=str(selected["instrument_key"]).strip(),
        trading_symbol=trading_symbol,
        display_name=display_name,
        segment=segment,
    )


def fetch_option_chain(
    token: str,
    expiry_value: str,
    request_json_fn: JsonRequest | None = None,
    instrument_key: str = NIFTY_INSTRUMENT_KEY,
) -> list[OptionChainRow]:
    """Fetch and normalize an underlying's option chain for one expiry."""
    fetch = request_json_fn or request_json
    payload = fetch(
        "/v2/option/chain",
        {"instrument_key": instrument_key, "expiry_date": expiry_value},
        token,
    )
    raw_rows = payload.get("data")
    if not isinstance(raw_rows, list):
        raise UpstoxError("Upstox returned no option-chain rows.")
    rows: list[OptionChainRow] = []
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            continue
        strike = _float_or_none(raw_row.get("strike_price"))
        if strike is None:
            continue
        rows.append(
            OptionChainRow(
                strike=strike,
                expiry=str(raw_row.get("expiry") or "n/a"),
                spot=_float_or_none(raw_row.get("underlying_spot_price")),
                call=_parse_option_side(raw_row.get("call_options")),
                put=_parse_option_side(raw_row.get("put_options")),
            )
        )
    if not rows:
        raise UpstoxError("Upstox returned no usable option-chain rows.")
    return sorted(rows, key=lambda row: row.strike)


def fetch_option_expiries(
    token: str,
    instrument_key: str,
    display_name: str,
    request_json_fn: JsonRequest | None = None,
    as_of: dt.date | None = None,
) -> list[OptionExpiry]:
    """Fetch, de-duplicate, and sort one underlying's available expiries."""
    fetch = request_json_fn or request_json
    payload = fetch(
        "/v2/option/contract",
        {"instrument_key": instrument_key},
        token,
    )
    raw_rows = payload.get("data")
    if not isinstance(raw_rows, list):
        raise UpstoxError(f"Upstox returned no {display_name} option contracts.")
    current_date = as_of or dt.datetime.now(ZoneInfo("Asia/Kolkata")).date()
    weekly_by_expiry: dict[str, bool] = {}
    lot_sizes_by_expiry: dict[str, set[int]] = {}
    for raw_row in raw_rows:
        if not isinstance(raw_row, dict):
            continue
        raw_expiry = str(raw_row.get("expiry") or "").strip()
        try:
            expiry_date = dt.date.fromisoformat(raw_expiry)
        except ValueError:
            continue
        if expiry_date < current_date:
            continue
        weekly = bool(raw_row.get("weekly"))
        # If either contract classification is monthly, preserve the monthly designation.
        weekly_by_expiry[raw_expiry] = weekly_by_expiry.get(raw_expiry, True) and weekly
        lot_size = _positive_int_or_none(raw_row.get("lot_size"))
        if lot_size is not None:
            lot_sizes_by_expiry.setdefault(raw_expiry, set()).add(lot_size)
    if not weekly_by_expiry:
        raise UpstoxError(
            f"{display_name} has no current option contracts on Upstox; it may not be an F&O underlying."
        )
    return [
        OptionExpiry(
            expiry,
            weekly_by_expiry[expiry],
            next(iter(lot_sizes_by_expiry.get(expiry, set())))
            if len(lot_sizes_by_expiry.get(expiry, set())) == 1
            else None,
        )
        for expiry in sorted(weekly_by_expiry)
    ]


def resolve_chain_contract(
    token: str,
    request: ChainRequest,
    instrument_key: str = NIFTY_INSTRUMENT_KEY,
    display_name: str = "NIFTY",
    request_json_fn: JsonRequest | None = None,
    as_of: dt.date | None = None,
) -> OptionExpiry:
    """Resolve a chain request to one listed expiry and its lot size."""
    expiries = fetch_option_expiries(
        token,
        instrument_key,
        display_name,
        request_json_fn,
        as_of,
    )
    if request.qualifier == "expiry":
        exact = next((item for item in expiries if item.expiry == request.expiry_value), None)
        if exact is None:
            raise UpstoxError(
                f"No {display_name} option expiry is listed for {request.expiry_value}."
            )
        return exact

    # Positional qualifiers describe the next three listed expiries, independent of calendar gaps.
    qualifier_index = {"near": 0, "next": 1, "far": 2}
    if request.qualifier in qualifier_index:
        index = qualifier_index[request.qualifier]
        if index >= len(expiries):
            raise UpstoxError(
                f"No {request.qualifier} {display_name} option expiry is currently available."
            )
        return expiries[index]
    if request.qualifier == "month":
        monthly = next((item for item in expiries if not item.weekly), None)
        if monthly is None:
            raise UpstoxError(f"No monthly {display_name} option expiry is currently available.")
        return monthly
    raise UpstoxError(f"Unsupported option expiry qualifier '{request.qualifier}'.")


def resolve_chain_expiry(
    token: str,
    request: ChainRequest,
    instrument_key: str = NIFTY_INSTRUMENT_KEY,
    display_name: str = "NIFTY",
    request_json_fn: JsonRequest | None = None,
    as_of: dt.date | None = None,
) -> str:
    """Resolve a chain qualifier to its listed expiry-date string."""
    return resolve_chain_contract(
        token,
        request,
        instrument_key,
        display_name,
        request_json_fn,
        as_of,
    ).expiry


def fetch_underlying_quote(
    token: str,
    instrument_key: str,
    display_name: str,
    request_json_fn: JsonRequest | None = None,
) -> UnderlyingQuote:
    """Fetch one option underlying's current value and previous close."""
    fetch = request_json_fn or request_json
    payload = fetch(
        "/v3/market-quote/ltp",
        {"instrument_key": instrument_key},
        token,
    )
    data = payload.get("data")
    if not isinstance(data, dict) or not data:
        raise UpstoxError(f"Upstox returned no {display_name} quote.")
    quote = next((value for value in data.values() if isinstance(value, dict)), None)
    if quote is None:
        raise UpstoxError(f"Upstox returned no usable {display_name} quote.")
    return UnderlyingQuote(
        last_price=_float_or_none(quote.get("last_price")),
        close_price=_float_or_none(quote.get("cp")),
    )


def fetch_full_market_quotes(
    token: str,
    instrument_keys: list[str],
    request_json_fn: JsonRequest | None = None,
) -> dict[str, FullMarketQuote]:
    """Fetch current-session quote ranges for one or more instruments."""
    unique_keys = list(dict.fromkeys(key.strip() for key in instrument_keys if key.strip()))
    if not unique_keys:
        raise UpstoxError("No instruments are available for the option-detail quote.")
    fetch = request_json_fn or request_json
    payload = fetch(
        "/v2/market-quote/quotes",
        {"instrument_key": ",".join(unique_keys)},
        token,
    )
    data = payload.get("data")
    if not isinstance(data, dict) or not data:
        raise UpstoxError("Upstox returned no full market quotes.")

    quotes: dict[str, FullMarketQuote] = {}
    for raw_quote in data.values():
        if not isinstance(raw_quote, dict):
            continue
        instrument_key = str(
            raw_quote.get("instrument_token") or raw_quote.get("instrument_key") or ""
        ).strip()
        if not instrument_key:
            continue
        ohlc = raw_quote.get("ohlc") if isinstance(raw_quote.get("ohlc"), dict) else {}
        quotes[instrument_key] = FullMarketQuote(
            instrument_key=instrument_key,
            last_price=_float_or_none(raw_quote.get("last_price")),
            close_price=_float_or_none(ohlc.get("close")),
            open_price=_float_or_none(ohlc.get("open")),
            day_high=_float_or_none(ohlc.get("high")),
            day_low=_float_or_none(ohlc.get("low")),
            timestamp=str(raw_quote.get("timestamp") or "").strip() or None,
        )
    if not quotes:
        raise UpstoxError("Upstox returned no usable full market quotes.")
    return quotes


def find_option_strike(
    rows: list[OptionChainRow],
    strike: float,
    display_name: str,
    expiry: str,
) -> OptionChainRow:
    """Return one exactly listed strike or raise an error with nearby alternatives."""
    exact = next(
        (row for row in rows if math.isclose(row.strike, strike, rel_tol=0.0, abs_tol=1e-6)),
        None,
    )
    if exact is not None:
        return exact

    # Nearby alternatives make copied or mistyped strikes easy to correct without substitution.
    nearest = sorted(rows, key=lambda row: (abs(row.strike - strike), row.strike))[:3]
    nearby = sorted(row.strike for row in nearest)

    def format_strike(value: float) -> str:
        """Format one suggested strike without unnecessary decimal zeroes."""
        return f"{value:,.2f}".rstrip("0").rstrip(".")

    suggestion = ""
    if nearby:
        suggestion = f" Nearby listed strikes: {', '.join(format_strike(value) for value in nearby)}."
    raise UpstoxError(
        f"Strike {format_strike(strike)} is not listed for {display_name} expiry {expiry}.{suggestion}"
    )


def window_around_atm(
    rows: list[OptionChainRow],
    spot: float,
    strikes_each_side: int,
) -> tuple[list[OptionChainRow], float]:
    """Return ATM plus the requested lower and higher strike wings."""
    if not rows:
        raise UpstoxError("No option strikes are available.")
    ordered = sorted(rows, key=lambda row: row.strike)
    atm_index = min(range(len(ordered)), key=lambda index: (abs(ordered[index].strike - spot), ordered[index].strike))
    lower = ordered[max(0, atm_index - strikes_each_side) : atm_index]
    higher = ordered[atm_index + 1 : atm_index + 1 + strikes_each_side]
    selected = [*lower, ordered[atm_index], *higher]
    return sorted(selected, key=lambda row: row.strike, reverse=True), ordered[atm_index].strike
