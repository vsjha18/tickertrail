from __future__ import annotations

import datetime as dt
import json
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


class UpstoxError(RuntimeError):
    """Describe a safe, user-facing Upstox configuration or API failure."""


@dataclass(frozen=True)
class ChainRequest:
    """Describe one normalized NIFTY option-chain request."""

    qualifier: str
    expiry_value: str
    strikes_each_side: int = 10


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


@dataclass(frozen=True)
class OptionChainRow:
    """Hold both option sides for one strike in an expiry chain."""

    strike: float
    expiry: str
    spot: float | None
    call: OptionSide
    put: OptionSide


@dataclass(frozen=True)
class NiftyQuote:
    """Hold the current NIFTY value and previous session close."""

    last_price: float | None
    close_price: float | None


@dataclass(frozen=True)
class OptionExpiry:
    """Describe one available NIFTY expiry and whether it is weekly."""

    expiry: str
    weekly: bool


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
    """Parse expiry and strike-count modifiers for the NIFTY chain command."""
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


def _float_or_none(value: Any) -> float | None:
    """Convert one API scalar to float without propagating malformed data."""
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


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
    )


def fetch_option_chain(
    token: str,
    expiry_value: str,
    request_json_fn: JsonRequest | None = None,
) -> list[OptionChainRow]:
    """Fetch and normalize the NIFTY option chain for one expiry selector."""
    fetch = request_json_fn or request_json
    payload = fetch(
        "/v2/option/chain",
        {"instrument_key": NIFTY_INSTRUMENT_KEY, "expiry_date": expiry_value},
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


def fetch_nifty_option_expiries(
    token: str,
    request_json_fn: JsonRequest | None = None,
    as_of: dt.date | None = None,
) -> list[OptionExpiry]:
    """Fetch, de-duplicate, and sort currently available NIFTY expiries."""
    fetch = request_json_fn or request_json
    payload = fetch(
        "/v2/option/contract",
        {"instrument_key": NIFTY_INSTRUMENT_KEY},
        token,
    )
    raw_rows = payload.get("data")
    if not isinstance(raw_rows, list):
        raise UpstoxError("Upstox returned no NIFTY option contracts.")
    current_date = as_of or dt.datetime.now(ZoneInfo("Asia/Kolkata")).date()
    weekly_by_expiry: dict[str, bool] = {}
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
    if not weekly_by_expiry:
        raise UpstoxError("Upstox returned no current NIFTY option expiries.")
    return [
        OptionExpiry(expiry, weekly_by_expiry[expiry])
        for expiry in sorted(weekly_by_expiry)
    ]


def resolve_chain_expiry(
    token: str,
    request: ChainRequest,
    request_json_fn: JsonRequest | None = None,
    as_of: dt.date | None = None,
) -> str:
    """Resolve a chain qualifier against actual available NIFTY contracts."""
    if request.qualifier == "expiry":
        return request.expiry_value
    expiries = fetch_nifty_option_expiries(token, request_json_fn, as_of)

    # Positional qualifiers describe the next three listed expiries, independent of calendar gaps.
    qualifier_index = {"near": 0, "next": 1, "far": 2}
    if request.qualifier in qualifier_index:
        index = qualifier_index[request.qualifier]
        if index >= len(expiries):
            raise UpstoxError(f"No {request.qualifier} NIFTY option expiry is currently available.")
        return expiries[index].expiry
    if request.qualifier == "month":
        monthly = next((item for item in expiries if not item.weekly), None)
        if monthly is None:
            raise UpstoxError("No monthly NIFTY option expiry is currently available.")
        return monthly.expiry
    raise UpstoxError(f"Unsupported NIFTY expiry qualifier '{request.qualifier}'.")


def fetch_nifty_quote(
    token: str,
    request_json_fn: JsonRequest | None = None,
) -> NiftyQuote:
    """Fetch the current NIFTY value and previous session close."""
    fetch = request_json_fn or request_json
    payload = fetch(
        "/v3/market-quote/ltp",
        {"instrument_key": NIFTY_INSTRUMENT_KEY},
        token,
    )
    data = payload.get("data")
    if not isinstance(data, dict) or not data:
        raise UpstoxError("Upstox returned no NIFTY quote.")
    quote = next((value for value in data.values() if isinstance(value, dict)), None)
    if quote is None:
        raise UpstoxError("Upstox returned no usable NIFTY quote.")
    return NiftyQuote(
        last_price=_float_or_none(quote.get("last_price")),
        close_price=_float_or_none(quote.get("cp")),
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
