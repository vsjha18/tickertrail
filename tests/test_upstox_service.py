from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from tickertrail import upstox_service as service


class _FakeResponse:
    """Provide a context-managed byte response for HTTP unit tests."""

    def __init__(self, payload: object):
        """Encode one JSON-compatible response payload."""
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        """Return the fake response from a context manager."""
        return self

    def __exit__(self, *_args):
        """Close the fake response without suppressing exceptions."""
        return False

    def read(self) -> bytes:
        """Return the encoded response body."""
        return self.body

    def close(self) -> None:
        """Match the close hook used by urllib response wrappers."""


class _RawResponse(_FakeResponse):
    """Return a caller-supplied byte body for malformed-response tests."""

    def __init__(self, body: bytes):
        """Store one raw body without JSON encoding it."""
        self.body = body


class UpstoxServiceTests(unittest.TestCase):
    def test_token_save_load_status_and_validation_errors(self):
        """Persist the canonical token atomically and reject unusable values."""
        original_path = service.TOKEN_FILE
        try:
            with tempfile.TemporaryDirectory() as td:
                service.TOKEN_FILE = Path(td) / ".upstox_analytics_token"
                self.assertFalse(service.token_is_configured())
                saved = service.save_analytics_token("  abc@#!  ")
                self.assertEqual(saved, service.TOKEN_FILE)
                self.assertEqual(service.load_analytics_token(), "abc@#!")
                self.assertTrue(service.token_is_configured())
                self.assertEqual(os.stat(saved).st_mode & 0o777, 0o600)
                with self.assertRaisesRegex(service.UpstoxError, "cannot be empty"):
                    service.save_analytics_token("  ")
                saved.write_text("\n", encoding="utf-8")
                with self.assertRaisesRegex(service.UpstoxError, "file is empty"):
                    service.load_analytics_token()
        finally:
            service.TOKEN_FILE = original_path

    def test_token_save_surfaces_file_errors_without_leaking_value(self):
        """Keep token persistence errors concise and credential-free."""
        original_path = service.TOKEN_FILE
        try:
            service.TOKEN_FILE = Path("/not-used/token")
            with patch.object(Path, "write_text", side_effect=OSError("secret-value")):
                with self.assertRaisesRegex(service.UpstoxError, "Could not save Upstox token") as caught:
                    service.save_analytics_token("secret-value")
            self.assertNotIn("secret-value", str(caught.exception))
        finally:
            service.TOKEN_FILE = original_path

    def test_parse_chain_args_supports_relative_exact_and_strike_forms(self):
        """Normalize all agreed expiry qualifiers and strike-count modifiers."""
        expected = {
            (): ("near", "near", 10),
            ("near",): ("near", "near", 10),
            ("next",): ("next", "next", 10),
            ("far",): ("far", "far", 10),
            ("month",): ("month", "month", 10),
            ("next", "strikes", "15"): ("next", "next", 15),
            ("expiry", "2026-08-27", "strikes", "2"): ("expiry", "2026-08-27", 2),
        }
        for args, values in expected.items():
            with self.subTest(args=args):
                parsed, error = service.parse_chain_args(list(args))
                self.assertIsNone(error)
                self.assertIsNotNone(parsed)
                assert parsed is not None
                self.assertEqual((parsed.qualifier, parsed.expiry_value, parsed.strikes_each_side), values)

    def test_parse_chain_args_rejects_incomplete_and_invalid_grammar(self):
        """Report deterministic usage errors for malformed chain modifiers."""
        invalid = (
            (["expiry"], "Incomplete command"),
            (["expiry", "27-08-2026"], "Invalid expiry date"),
            (["next", "10"], "Usage:"),
            (["strikes", "many"], "whole number"),
            (["strikes", "0"], "from 1 to 25"),
            (["strikes", "26"], "from 1 to 25"),
        )
        for args, message in invalid:
            with self.subTest(args=args):
                parsed, error = service.parse_chain_args(args)
                self.assertIsNone(parsed)
                self.assertIn(message, error or "")

    def test_fetch_option_chain_normalizes_rows_and_skips_malformed_entries(self):
        """Normalize market data and Greeks from one mocked chain response."""
        calls: list[tuple[str, dict[str, str], str]] = []

        def fake_request(endpoint, params, token):
            """Return one deterministic option-chain payload."""
            calls.append((endpoint, params, token))
            return {
                "status": "success",
                "data": [
                    "bad",
                    {"strike_price": "bad"},
                    {
                        "expiry": "2026-08-20",
                        "strike_price": 24600,
                        "underlying_spot_price": 24590.5,
                        "call_options": {
                            "market_data": {"ltp": 151.8, "close_price": 150, "volume": 104000, "oi": 61000},
                            "option_greeks": {"iv": 11.8, "delta": 0.52, "gamma": 0.0014, "theta": -9.1, "vega": 11.4},
                        },
                        "put_options": None,
                    },
                    {
                        "expiry": "2026-08-20",
                        "strike_price": 24550,
                        "underlying_spot_price": 24590.5,
                        "call_options": {},
                        "put_options": {},
                    },
                ],
            }

        rows = service.fetch_option_chain(
            "token",
            "2026-08-20",
            fake_request,
            instrument_key="NSE_EQ|INE002A01018",
        )

        self.assertEqual([row.strike for row in rows], [24550.0, 24600.0])
        self.assertEqual(rows[1].call.delta, 0.52)
        self.assertEqual(rows[1].call.ltp, 151.8)
        self.assertIsNone(rows[1].put.ltp)
        self.assertEqual(calls[0][0], "/v2/option/chain")
        self.assertEqual(calls[0][1]["instrument_key"], "NSE_EQ|INE002A01018")
        self.assertEqual(calls[0][1]["expiry_date"], "2026-08-20")
        self.assertEqual(calls[0][2], "token")

    def test_fetch_option_chain_rejects_missing_or_unusable_data(self):
        """Reject successful-looking responses that contain no usable strikes."""
        with self.assertRaisesRegex(service.UpstoxError, "no option-chain rows"):
            service.fetch_option_chain("t", "2026-08-20", lambda *_args: {})
        with self.assertRaisesRegex(service.UpstoxError, "no usable"):
            service.fetch_option_chain(
                "t",
                "2026-08-20",
                lambda *_args: {"data": [{"strike_price": None}]},
            )

    def test_resolve_option_underlying_requires_an_exact_stock_or_index_match(self):
        """Prefer the requested exchange and reject fuzzy-only instrument matches."""
        payload = {
            "data": [
                {
                    "name": "RELIANCE INDUSTRIES LTD",
                    "segment": "NSE_EQ",
                    "exchange": "NSE",
                    "instrument_key": "NSE_EQ|INE002A01018",
                    "trading_symbol": "RELIANCE",
                    "short_name": "Reliance",
                },
                {
                    "name": "RELIANCE INDUSTRIES LTD.",
                    "segment": "BSE_EQ",
                    "exchange": "BSE",
                    "instrument_key": "BSE_EQ|INE002A01018",
                    "trading_symbol": "RELIANCE",
                    "short_name": "RELIANCE",
                },
                {
                    "name": "RELIANCE POWER LTD.",
                    "segment": "NSE_EQ",
                    "exchange": "NSE",
                    "instrument_key": "NSE_EQ|OTHER",
                    "trading_symbol": "RPOWER",
                    "short_name": "Reliance Power",
                },
                "bad",
            ]
        }
        calls: list[tuple[str, dict[str, str], str]] = []

        def fake_request(endpoint, params, token):
            """Record the instrument search and return deterministic candidates."""
            calls.append((endpoint, params, token))
            return payload

        underlying = service.resolve_option_underlying(
            "token", "reliance", fake_request, preferred_exchange="BSE"
        )
        self.assertEqual(underlying.instrument_key, "BSE_EQ|INE002A01018")
        self.assertEqual(underlying.display_name, "RELIANCE")
        self.assertEqual(calls[0][0], "/v2/instruments/search")
        self.assertEqual(calls[0][1]["segments"], "EQ,INDEX")
        with self.assertRaisesRegex(service.UpstoxError, "exactly match"):
            service.resolve_option_underlying("token", "rel", fake_request)
        with self.assertRaisesRegex(service.UpstoxError, "Enter a stock"):
            service.resolve_option_underlying("token", " ", fake_request)
        with self.assertRaisesRegex(service.UpstoxError, "could not resolve"):
            service.resolve_option_underlying("token", "INFY", lambda *_args: {})

    def test_fetch_and_resolve_actual_option_expiries(self):
        """Resolve relative qualifiers from live-contract dates rather than calendar keywords."""
        calls: list[tuple[str, dict[str, str], str]] = []

        def fake_request(endpoint, params, token):
            """Return repeated contracts across weekly and monthly expiries."""
            calls.append((endpoint, params, token))
            return {
                "data": [
                    "bad",
                    {"expiry": "invalid", "weekly": True},
                    {"expiry": "2026-08-11", "weekly": True},
                    {"expiry": "2026-08-18", "weekly": True},
                    {"expiry": "2026-08-18", "weekly": True},
                    {"expiry": "2026-08-25", "weekly": True},
                    {"expiry": "2026-08-25", "weekly": False},
                    {"expiry": "2026-09-01", "weekly": True},
                ]
            }

        expiries = service.fetch_option_expiries(
            "token",
            "NSE_EQ|INE002A01018",
            "RELIANCE",
            fake_request,
            as_of=dt.date(2026, 8, 13),
        )
        self.assertEqual(
            expiries,
            [
                service.OptionExpiry("2026-08-18", True),
                service.OptionExpiry("2026-08-25", False),
                service.OptionExpiry("2026-09-01", True),
            ],
        )
        self.assertEqual(
            calls[0],
            (
                "/v2/option/contract",
                {"instrument_key": "NSE_EQ|INE002A01018"},
                "token",
            ),
        )
        for qualifier, expected in (
            ("near", "2026-08-18"),
            ("next", "2026-08-25"),
            ("far", "2026-09-01"),
            ("month", "2026-08-25"),
        ):
            with self.subTest(qualifier=qualifier):
                request = service.ChainRequest(qualifier, service.EXPIRY_QUALIFIERS[qualifier])
                self.assertEqual(
                    service.resolve_chain_expiry(
                        "token",
                        request,
                        "NSE_EQ|INE002A01018",
                        "RELIANCE",
                        fake_request,
                        as_of=dt.date(2026, 8, 13),
                    ),
                    expected,
                )
        exact = service.ChainRequest("expiry", "2026-08-27")
        with self.assertRaisesRegex(service.UpstoxError, "2026-08-27"):
            service.resolve_chain_expiry(
                "token",
                exact,
                "NSE_EQ|INE002A01018",
                "RELIANCE",
                fake_request,
                as_of=dt.date(2026, 8, 13),
            )
        listed_exact = service.ChainRequest("expiry", "2026-08-25")
        self.assertEqual(
            service.resolve_chain_expiry(
                "token",
                listed_exact,
                "NSE_EQ|INE002A01018",
                "RELIANCE",
                fake_request,
                as_of=dt.date(2026, 8, 13),
            ),
            "2026-08-25",
        )

    def test_expiry_resolution_reports_unavailable_contracts(self):
        """Return useful failures for missing positional and monthly expiries."""
        with self.assertRaisesRegex(service.UpstoxError, "no RELIANCE option contracts"):
            service.fetch_option_expiries("t", "key", "RELIANCE", lambda *_args: {})
        with self.assertRaisesRegex(service.UpstoxError, "not be an F&O underlying"):
            service.fetch_option_expiries(
                "t", "key", "RELIANCE", lambda *_args: {"data": [{"expiry": "bad"}]}
            )
        weekly_only = lambda *_args: {
            "data": [{"expiry": "2026-08-18", "weekly": True}]
        }
        with self.assertRaisesRegex(service.UpstoxError, "No next"):
            service.resolve_chain_expiry(
                "t",
                service.ChainRequest("next", "next"),
                "key",
                "RELIANCE",
                weekly_only,
                as_of=dt.date(2026, 8, 13),
            )
        with self.assertRaisesRegex(service.UpstoxError, "No monthly"):
            service.resolve_chain_expiry(
                "t",
                service.ChainRequest("month", "month"),
                "key",
                "RELIANCE",
                weekly_only,
                as_of=dt.date(2026, 8, 13),
            )
        with self.assertRaisesRegex(service.UpstoxError, "Unsupported"):
            service.resolve_chain_expiry(
                "t",
                service.ChainRequest("later", "later"),
                "key",
                "RELIANCE",
                weekly_only,
                as_of=dt.date(2026, 8, 13),
            )

    def test_fetch_underlying_quote_normalizes_first_quote_block(self):
        """Extract underlying LTP and previous close from a mocked V3 quote."""
        quote = service.fetch_underlying_quote(
            "token",
            "NSE_EQ|INE002A01018",
            "RELIANCE",
            lambda endpoint, params, token: {
                "data": {"NSE_INDEX:Nifty 50": {"last_price": "24619.35", "cp": 24490.95}}
            },
        )
        self.assertEqual(quote, service.UnderlyingQuote(24619.35, 24490.95))
        with self.assertRaisesRegex(service.UpstoxError, "no RELIANCE quote"):
            service.fetch_underlying_quote("token", "key", "RELIANCE", lambda *_args: {"data": {}})
        with self.assertRaisesRegex(service.UpstoxError, "no usable"):
            service.fetch_underlying_quote(
                "token", "key", "RELIANCE", lambda *_args: {"data": {"x": "bad"}}
            )

    def test_window_around_atm_returns_descending_spine(self):
        """Select symmetric wings and render higher strikes first."""
        empty_side = service.OptionSide(None, None, None, None, None, None, None, None, None)
        rows = [service.OptionChainRow(float(strike), "2026-08-20", 24575, empty_side, empty_side) for strike in range(24400, 24801, 50)]
        selected, atm = service.window_around_atm(rows, 24575, 2)
        self.assertEqual(atm, 24550.0)
        self.assertEqual([row.strike for row in selected], [24650.0, 24600.0, 24550.0, 24500.0, 24450.0])
        with self.assertRaisesRegex(service.UpstoxError, "No option strikes"):
            service.window_around_atm([], 1.0, 2)

    def test_request_json_builds_authorized_get_and_handles_failures(self):
        """Exercise authenticated HTTP decoding without making a live request."""
        with patch("tickertrail.upstox_service.urlopen", return_value=_FakeResponse({"status": "success"})) as mock_open:
            payload = service.request_json("/v2/test", {"instrument_key": "NSE_INDEX|Nifty 50"}, "abc")
        self.assertEqual(payload, {"status": "success"})
        request = mock_open.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer abc")
        self.assertEqual(request.get_header("User-agent"), service.USER_AGENT)
        self.assertIn("instrument_key=NSE_INDEX%7CNifty+50", request.full_url)

        error = HTTPError("https://x", 401, "bad", {}, _FakeResponse({"errors": [{"message": "Invalid token"}]}))
        with patch("tickertrail.upstox_service.urlopen", side_effect=error):
            with self.assertRaisesRegex(service.UpstoxError, "Invalid token"):
                service.request_json("/v2/test", {}, "abc")
        with patch("tickertrail.upstox_service.urlopen", side_effect=URLError("offline")):
            with self.assertRaisesRegex(service.UpstoxError, "Could not reach"):
                service.request_json("/v2/test", {}, "abc")

    def test_request_json_reports_safe_fallback_errors(self):
        """Cover malformed bodies, generic HTTP errors, and auth fallbacks."""
        cases = (
            (
                HTTPError("https://x", 403, "bad", {}, _RawResponse(b"not-json")),
                "denied access",
            ),
            (
                HTTPError("https://x", 429, "bad", {}, _FakeResponse({})),
                "HTTP 429",
            ),
            (
                HTTPError("https://x", 400, "bad", {}, _FakeResponse({"message": "Bad request"})),
                "Bad request",
            ),
            (
                HTTPError(
                    "https://x",
                    403,
                    "bad",
                    {},
                    _FakeResponse(
                        {
                            "cloudflare_error": True,
                            "error_code": 1010,
                            "detail": "The site owner blocked this browser signature.",
                        }
                    ),
                ),
                "gateway blocked.*1010.*browser signature",
            ),
        )
        for error, message in cases:
            with self.subTest(message=message):
                with patch("tickertrail.upstox_service.urlopen", side_effect=error):
                    with self.assertRaisesRegex(service.UpstoxError, message):
                        service.request_json("/v2/test", {}, "abc")

        with patch("tickertrail.upstox_service.urlopen", return_value=_RawResponse(b"not-json")):
            with self.assertRaisesRegex(service.UpstoxError, "unreadable response"):
                service.request_json("/v2/test", {}, "abc")
        with patch("tickertrail.upstox_service.urlopen", return_value=_FakeResponse([])):
            with self.assertRaisesRegex(service.UpstoxError, "unexpected response"):
                service.request_json("/v2/test", {}, "abc")
        with patch("tickertrail.upstox_service.urlopen", side_effect=TimeoutError("slow")):
            with self.assertRaisesRegex(service.UpstoxError, "Could not reach"):
                service.request_json("/v2/test", {}, "abc")


if __name__ == "__main__":
    unittest.main()
