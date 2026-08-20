from __future__ import annotations

import datetime as dt
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tickertrail import cli
from tickertrail import upstox_service as service


def _side(
    ltp: float,
    close: float,
    delta: float,
    instrument_key: str | None = None,
) -> service.OptionSide:
    """Build one complete deterministic option side for rendering tests."""
    return service.OptionSide(
        ltp=ltp,
        close_price=close,
        volume=85000,
        oi=42000,
        iv=11.6,
        delta=delta,
        gamma=0.0014,
        theta=-9.1,
        vega=11.4,
        instrument_key=instrument_key,
        bid_price=ltp - 0.1,
        bid_qty=3250,
        ask_price=ltp + 0.05,
        ask_qty=1950,
        prev_oi=40000,
        pop=48.0,
    )


def _chain_rows() -> list[service.OptionChainRow]:
    """Build a small chain around a 24,600 ATM strike."""
    return [
        service.OptionChainRow(float(strike), "2026-08-20", 24590.0, _side(120 + offset, 110, 0.52), _side(120 - offset, 125, -0.48))
        for offset, strike in enumerate(range(24450, 24751, 50))
    ]


def _detail_rows() -> list[service.OptionChainRow]:
    """Build deterministic NIFTY rows with instrument keys around the requested strike."""
    return [
        service.OptionChainRow(
            float(strike),
            "2026-08-25",
            24197.1,
            _side(
                128.7 + ((strike - 24200) / 10),
                80.4,
                0.601,
                f"NSE_FO|CALL{strike}",
            ),
            _side(
                70.45 - ((strike - 24200) / 10),
                163.25,
                -0.401,
                f"NSE_FO|PUT{strike}",
            ),
        )
        for strike in (24150, 24200, 24250)
    ]


def _detail_quotes() -> dict[str, service.FullMarketQuote]:
    """Build grouped underlying, call, and put quotes with current-session ranges."""
    return {
        "NSE_INDEX|Nifty 50": service.FullMarketQuote(
            "NSE_INDEX|Nifty 50",
            24197.1,
            24078.3,
            24190.0,
            24226.85,
            24184.55,
            "1787195765000",
        ),
        "NSE_FO|CALL24200": service.FullMarketQuote(
            "NSE_FO|CALL24200", 128.7, 80.4, 81.0, 132.4, 79.8, None
        ),
        "NSE_FO|PUT24200": service.FullMarketQuote(
            "NSE_FO|PUT24200", 70.45, 163.25, 160.0, 166.25, 68.7, None
        ),
    }


class UpstoxCliTests(unittest.TestCase):
    def test_config_adds_token_and_root_show_reports_status(self):
        """Keep token writes in config mode and status reads in normal mode."""
        original_path = service.TOKEN_FILE
        try:
            with tempfile.TemporaryDirectory() as td:
                service.TOKEN_FILE = Path(td) / ".upstox_analytics_token"
                commands = [
                    "config",
                    "?",
                    "help token",
                    "token",
                    "token add other abc",
                    "token add upstox @#@#@#!",
                    "token status upstox",
                    "end",
                    "show token",
                    "show token upstox",
                    "show token other",
                    "show",
                    "end",
                    "exit",
                ]
                with (
                    patch("tickertrail.cli._enable_repl_history", return_value=None),
                    patch("builtins.input", side_effect=commands) as mock_input,
                    patch("sys.stdout", new_callable=io.StringIO) as out,
                    patch("sys.stderr", new_callable=io.StringIO) as err,
                ):
                    rc = cli._run_repl(None, None, None, 100, 22)

                self.assertEqual(rc, 0)
                self.assertEqual(service.load_analytics_token(), "@#@#@#!")
                self.assertIn("Commands available here (config)", out.getvalue())
                self.assertIn("Command: token", out.getvalue())
                self.assertIn("analytics token saved", out.getvalue())
                self.assertIn("configured", out.getvalue())
                self.assertGreaterEqual(
                    sum(call.args[0] == "tt>config> " for call in mock_input.call_args_list),
                    7,
                )
                self.assertIn("Incomplete command", err.getvalue())
                self.assertIn("unavailable in config mode", err.getvalue())
                self.assertGreaterEqual(err.getvalue().count("Usage: show token [upstox]"), 2)
                self.assertIn("available only in config mode", err.getvalue())
        finally:
            service.TOKEN_FILE = original_path

    def test_config_mode_exit_and_unknown_command_paths(self):
        """Return config mode to root and reject unrelated config commands."""
        with (
            patch("tickertrail.cli._enable_repl_history", return_value=None),
            patch(
                "builtins.input",
                side_effect=["config x", "config", "bogus", "exit", "exit"],
            ) as mock_input,
            patch("tickertrail.cli._print_quote", return_value=0),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = cli._run_repl("nifty", "^NSEI", {"regularMarketPrice": 1.0}, 100, 22)
        self.assertEqual(rc, 0)
        self.assertIn("Usage: config", err.getvalue())
        self.assertIn("Unknown config command", err.getvalue())
        prompts = [call.args[0] for call in mock_input.call_args_list]
        self.assertEqual(prompts[-1], "tt> ")

    def test_chain_parser_resolves_contextual_and_explicit_underlyings(self):
        """Accept stock/index context and explicit one-shot F&O targets."""
        target, contextual, error = cli._parse_chain_command(["next", "strikes", "3"], "RELIANCE.NS")
        self.assertIsNone(error)
        self.assertEqual(target, cli._OptionChainTarget("RELIANCE", "NSE"))
        self.assertEqual(contextual, service.ChainRequest("next", "next", 3))
        target, one_shot, error = cli._parse_chain_command(["bank", "month"], None)
        self.assertIsNone(error)
        self.assertEqual(target, cli._OptionChainTarget("NIFTY BANK", "NSE"))
        self.assertEqual(one_shot, service.ChainRequest("month", "month", 10))
        target, contextual, error = cli._parse_chain_command([], "^BSESN")
        self.assertIsNone(error)
        self.assertEqual(target, cli._OptionChainTarget("SENSEX", "BSE"))
        self.assertEqual(contextual, service.ChainRequest("near", "near", 10))
        target, one_shot, error = cli._parse_chain_command(["midcapselect"], None)
        self.assertIsNone(error)
        self.assertEqual(target, cli._OptionChainTarget("NIFTY MID SELECT", "NSE"))
        self.assertEqual(one_shot, service.ChainRequest("near", "near", 10))
        target, rejected, error = cli._parse_chain_command(["next"], None)
        self.assertIsNone(target)
        self.assertIsNone(rejected)
        self.assertIn("No active stock or index", error or "")

    def test_option_detail_parser_resolves_contextual_and_explicit_targets(self):
        """Parse contextual strikes, explicit targets, grouping commas, and errors."""
        target, request, error = cli._parse_option_detail_command(
            ["24,200", "next"], "^NSEI"
        )
        self.assertIsNone(error)
        self.assertEqual(target, cli._OptionChainTarget("NIFTY 50", "NSE"))
        self.assertEqual(request, service.OptionDetailRequest(24200, "next", "next"))

        target, request, error = cli._parse_option_detail_command(
            ["reliance", "1400.50", "month"], None
        )
        self.assertIsNone(error)
        self.assertEqual(target, cli._OptionChainTarget("RELIANCE", "NSE"))
        self.assertEqual(request, service.OptionDetailRequest(1400.5, "month", "month"))

        for args, current, message in (
            ([], "^NSEI", "Incomplete command"),
            (["24200"], None, "No active stock or index"),
            (["nifty"], None, "Incomplete command"),
            (["nifty", "bad"], None, "positive number"),
        ):
            with self.subTest(args=args):
                rejected_target, rejected_request, parse_error = cli._parse_option_detail_command(
                    args, current
                )
                self.assertIsNone(rejected_target)
                self.assertIsNone(rejected_request)
                self.assertIn(message, parse_error or "")

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_option_chain", return_value=0)
    @patch("tickertrail.cli._print_quote", return_value=0)
    def test_repl_routes_chain_alias_qualifiers_and_help(self, _mock_quote, mock_chain, _mock_hist):
        """Dispatch contextual chain variants without resolving new symbols."""
        with (
            patch("builtins.input", side_effect=["chain", "chain next strikes 3", "oc far", "chain ?", "exit"]),
            patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            rc = cli._run_repl("nifty", "^NSEI", {"regularMarketPrice": 1.0}, 100, 22)
        self.assertEqual(rc, 0)
        self.assertEqual(
            [call.args for call in mock_chain.call_args_list],
            [
                (cli._OptionChainTarget("NIFTY 50", "NSE"), service.ChainRequest("near", "near", 10)),
                (cli._OptionChainTarget("NIFTY 50", "NSE"), service.ChainRequest("next", "next", 3)),
                (cli._OptionChainTarget("NIFTY 50", "NSE"), service.ChainRequest("far", "far", 10)),
            ],
        )
        self.assertIn("Command: chain", out.getvalue())
        self.assertNotIn("chain <symbol|index>", out.getvalue())
        self.assertIn("Use the active stock/index", out.getvalue())

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_option_chain", return_value=0)
    def test_repl_routes_root_chain_targets_and_requires_an_explicit_target(self, mock_chain, _mock_hist):
        """Route root stock/index targets and reject a missing target without networking."""
        with (
            patch("builtins.input", side_effect=["chain", "chain nifty month", "chain reliance next", "exit"]),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = cli._run_repl(None, None, None, 100, 22)
        self.assertEqual(rc, 0)
        self.assertEqual(
            [call.args for call in mock_chain.call_args_list],
            [
                (cli._OptionChainTarget("NIFTY 50", "NSE"), service.ChainRequest("month", "month", 10)),
                (cli._OptionChainTarget("RELIANCE", "NSE"), service.ChainRequest("next", "next", 10)),
            ],
        )
        self.assertIn("No active stock or index", err.getvalue())

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_option_detail", return_value=0)
    @patch("tickertrail.cli._print_quote", return_value=0)
    def test_repl_routes_option_detail_aliases_and_contextual_help(
        self, _mock_quote, mock_detail, _mock_hist
    ):
        """Dispatch contextual opt aliases and intercept situational help without networking."""
        with (
            patch(
                "builtins.input",
                side_effect=[
                    "opt 24200",
                    "option 24,200 next",
                    "opt 24200 expiry 2026-08-27",
                    "opt ?",
                    "exit",
                ],
            ),
            patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            rc = cli._run_repl("nifty", "^NSEI", {"regularMarketPrice": 1.0}, 100, 22)
        self.assertEqual(rc, 0)
        self.assertEqual(
            [call.args for call in mock_detail.call_args_list],
            [
                (
                    cli._OptionChainTarget("NIFTY 50", "NSE"),
                    service.OptionDetailRequest(24200, "near", "near"),
                ),
                (
                    cli._OptionChainTarget("NIFTY 50", "NSE"),
                    service.OptionDetailRequest(24200, "next", "next"),
                ),
                (
                    cli._OptionChainTarget("NIFTY 50", "NSE"),
                    service.OptionDetailRequest(24200, "expiry", "2026-08-27"),
                ),
            ],
        )
        self.assertIn("Command: opt", out.getvalue())
        self.assertNotIn("opt <symbol|index>", out.getvalue())

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_option_detail", return_value=0)
    def test_repl_routes_explicit_option_detail_and_rejects_root_bare_strike(
        self, mock_detail, _mock_hist
    ):
        """Require explicit underlying targets outside stock or index context."""
        with (
            patch(
                "builtins.input",
                side_effect=["opt 24200", "opt nifty 24200 next", "option reliance 1400", "exit"],
            ),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = cli._run_repl(None, None, None, 100, 22)
        self.assertEqual(rc, 0)
        self.assertEqual(len(mock_detail.call_args_list), 2)
        self.assertIn("No active stock or index", err.getvalue())

    def test_render_chain_has_descending_bold_spine_headers_and_atm_row(self):
        """Render bold headers/spine/ATM with independent option-side colours."""
        with (
            patch("tickertrail.cli._supports_color", return_value=True),
            patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            cli._render_option_chain(
                service.ChainRequest("near", "near", 2),
                _chain_rows(),
                service.NiftyQuote(24590.0, 24460.0),
                "Nifty 50",
                65,
            )
        rendered = out.getvalue()
        plain = cli._ANSI_ESCAPE_RE.sub("", rendered)
        self.assertIn("NIFTY 50  24,590.00  +130.00 (+0.53%) ↑", plain)
        self.assertIn("Expiry 20-Aug-2026", plain)
        self.assertIn("ATM 24,600 · Lot size 65 · 2 strikes below/above", plain)
        self.assertIn("Delta         LTP (Today) │", plain)
        self.assertIn("│ LTP (Today)           Delta", plain)
        self.assertIn("Theta", plain)
        self.assertNotIn("Gamma", plain)
        self.assertNotIn("Vega", plain)
        self.assertNotIn("IV%", plain)
        self.assertLessEqual(max(len(line) for line in plain.splitlines()), 120)
        self.assertLess(plain.index("24,700"), plain.index("24,600 ATM"))
        self.assertLess(plain.index("24,600 ATM"), plain.index("24,500"))
        self.assertIn("\033[1m", rendered)
        self.assertIn("\033[1;32m", rendered)
        self.assertIn("\033[1;31m", rendered)

    def test_render_chain_falls_back_to_spot_and_handles_missing_changes(self):
        """Use chain spot when the separate NIFTY quote is unavailable."""
        rows = _chain_rows()
        rows[0] = service.OptionChainRow(
            rows[0].strike,
            rows[0].expiry,
            rows[0].spot,
            service.OptionSide(None, None, None, None, None, None, None, None, None),
            rows[0].put,
        )
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            cli._render_option_chain(
                service.ChainRequest("far", "far", 1), rows, None, "Nifty 50", None
            )
        self.assertIn("24,590.00  n/a", out.getvalue())
        self.assertIn("Lot size n/a", out.getvalue())
        self.assertIn("n/a", out.getvalue())

    def test_render_option_detail_shows_ranges_calculations_and_semantic_colors(self):
        """Render the approved two-sided visual drill-down with deterministic calculations."""
        rows = _detail_rows()
        underlying = service.OptionUnderlying(
            "NSE_INDEX|Nifty 50", "NIFTY", "Nifty 50", "NSE_INDEX"
        )
        with (
            patch("tickertrail.cli._supports_color", return_value=True),
            patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            cli._render_option_detail(
                service.OptionDetailRequest(24200, "near", "near"),
                rows[1],
                rows,
                _detail_quotes(),
                underlying,
                65,
                now=dt.datetime(2026, 8, 20, 11, 26, 5),
            )
        rendered = out.getvalue()
        plain = cli._ANSI_ESCAPE_RE.sub("", rendered)
        self.assertIn("NIFTY 50  24,197.10  +118.80 (+0.49%) ↑", plain)
        self.assertIn("OPTION DETAIL · NEAR · Expiry 25-Aug-2026 · 5 calendar days", plain)
        self.assertIn("Strike 24,200 · ATM · Lot size 65", plain)
        self.assertIn("Underlying Day Range", plain)
        self.assertIn("24,184.55 .. 24,226.85", plain)
        self.assertIn("CALL Day Range", plain)
        self.assertIn("79.80 .. 132.40", plain)
        self.assertIn("PUT Day Range", plain)
        self.assertIn("68.70 .. 166.25", plain)
        self.assertIn("128.70  +48.30 (+60.07%) ↑", plain)
        self.assertIn("70.45  -92.80 (-56.85%) ↓", plain)
        self.assertIn("128.60 × 3.25K", plain)
        self.assertIn("128.75 × 1.95K", plain)
        self.assertIn("0.15 (0.12%)", plain)
        self.assertIn("+2.00K (+5.00%)", plain)
        self.assertIn("Implied volatility", plain)
        self.assertIn("11.60%", plain)
        self.assertIn("ATM · OTM by 2.90", plain)
        self.assertIn("ATM · ITM by 2.90", plain)
        self.assertIn("₹8,365.50", plain)
        self.assertIn("₹4,579.25", plain)
        self.assertIn("24,328.70", plain)
        self.assertIn("24,129.55", plain)
        self.assertLessEqual(max(len(line) for line in plain.splitlines()), 100)
        self.assertIn("\033[1;36m", rendered)
        self.assertIn("\033[1;33m", rendered)
        self.assertIn("\033[32m", rendered)
        self.assertIn("\033[31m", rendered)

    def test_option_detail_helpers_and_rendering_handle_sparse_data(self):
        """Render sparse provider fields as n/a and cover defensive detail calculations."""
        empty = service.OptionSide(None, None, None, None, None, None, None, None, None)
        crossed = service.OptionSide(
            10, 10, 1, 1, 1, 0.5, 0.1, -1, 1, bid_price=11, ask_price=10
        )
        zero_book = service.OptionSide(
            10, 10, 1, 1, 1, 0.5, 0.1, -1, 1, bid_price=0, ask_price=0
        )
        self.assertEqual(cli._format_option_spread(crossed), "n/a")
        self.assertEqual(cli._format_option_spread(zero_book), "0.00 (n/a)")
        self.assertEqual(cli._format_option_market_level(None, None), "n/a")
        self.assertEqual(cli._format_option_detail_ltp(empty), ("n/a", "gray"))
        self.assertEqual(cli._format_option_oi_change(empty), ("n/a", "gray"))
        self.assertEqual(cli._format_option_detail_scalar(None), "n/a")
        self.assertEqual(cli._option_moneyness(100, 100, "call", True), "ATM")
        self.assertEqual(cli._option_moneyness(101, 100, "call", False), "ITM by 1.00")
        self.assertEqual(cli._option_moneyness(101, 100, "put", False), "OTM by 1.00")

        rows = [service.OptionChainRow(100, "n/a", 101, empty, empty)]
        underlying = service.OptionUnderlying("key", "TEST", "Test", "NSE_INDEX")
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            cli._render_option_detail(
                service.OptionDetailRequest(100, "expiry", "n/a"),
                rows[0],
                rows,
                {},
                underlying,
                None,
                now=dt.datetime(2026, 8, 20, 11, 26, 5),
            )
        text = out.getvalue()
        self.assertIn("calendar days n/a", text)
        self.assertIn("Lot size n/a", text)
        self.assertEqual(
            sum("Day Range" in line and line.endswith("n/a") for line in text.splitlines()),
            3,
        )

        no_spot = [service.OptionChainRow(100, "2026-08-25", None, empty, empty)]
        with self.assertRaisesRegex(service.UpstoxError, "no current Test value"):
            cli._render_option_detail(
                service.OptionDetailRequest(100, "near", "near"),
                no_spot[0],
                no_spot,
                {},
                underlying,
                None,
                now=dt.datetime(2026, 8, 20),
            )

    def test_chain_expiry_label_preserves_non_iso_values(self):
        """Keep an unexpected expiry readable instead of failing rendering."""
        self.assertEqual(cli._format_chain_expiry_label("n/a"), "n/a")
        self.assertEqual(cli._format_chain_scalar(-829957.89, 2), "-830.0K")
        self.assertLessEqual(len(cli._format_chain_scalar(1e18, 2)), 7)

    def test_chain_helpers_handle_missing_values_and_token_save_error(self):
        """Render absent market fields safely and surface token persistence errors."""
        empty = service.OptionSide(None, None, None, None, None, None, None, None, None)
        no_close = service.OptionSide(10.0, None, None, None, None, None, None, None, None)
        self.assertEqual(cli._format_option_ltp(empty), "n/a")
        self.assertEqual(cli._format_option_ltp(no_close), "10.00 (n/a)")
        self.assertEqual(cli._option_side_color(empty), "gray")
        with (
            patch(
                "tickertrail.cli.upstox_service.save_analytics_token",
                side_effect=service.UpstoxError("save failed"),
            ),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            cli._handle_config_token_command("token add upstox abc")
        self.assertIn("save failed", err.getvalue())

        missing_spot_rows = [
            service.OptionChainRow(24600.0, "2026-08-20", None, empty, empty)
        ]
        with self.assertRaisesRegex(service.UpstoxError, "no current RELIANCE value"):
            cli._render_option_chain(
                service.ChainRequest("near", "near", 10),
                missing_spot_rows,
                None,
                "RELIANCE",
                500,
            )

    def test_print_chain_fetches_quote_and_chain_with_spot_fallback(self):
        """Track both Upstox calls and tolerate a failed header quote."""
        request = service.ChainRequest("near", "near", 2)
        target = cli._OptionChainTarget("RELIANCE", "NSE")
        underlying = service.OptionUnderlying(
            "NSE_EQ|INE002A01018", "RELIANCE", "RELIANCE", "NSE_EQ"
        )
        with (
            patch("tickertrail.cli.upstox_service.load_analytics_token", return_value="token"),
            patch("tickertrail.cli.upstox_service.resolve_option_underlying", return_value=underlying) as mock_underlying,
            patch("tickertrail.cli.upstox_service.fetch_underlying_quote", side_effect=service.UpstoxError("quote down")),
            patch(
                "tickertrail.cli.upstox_service.resolve_chain_contract",
                return_value=service.OptionExpiry("2026-08-18", True, 500),
            ) as mock_expiry,
            patch("tickertrail.cli.upstox_service.fetch_option_chain", return_value=_chain_rows()) as mock_chain,
            patch("tickertrail.cli._render_option_chain") as mock_render,
        ):
            cli._reset_network_call_metrics()
            rc = cli._print_option_chain(target, request)
        self.assertEqual(rc, 0)
        mock_underlying.assert_called_once_with(
            "token", "RELIANCE", preferred_exchange="NSE"
        )
        mock_expiry.assert_called_once_with(
            "token", request, "NSE_EQ|INE002A01018", "RELIANCE"
        )
        mock_chain.assert_called_once_with(
            "token", "2026-08-18", instrument_key="NSE_EQ|INE002A01018"
        )
        mock_render.assert_called_once_with(request, unittest.mock.ANY, None, "RELIANCE", 500)
        self.assertEqual(
            cli._NETWORK_CALL_COUNTS,
            {
                "upstox.instrument_search": 1,
                "upstox.option_contract": 1,
                "upstox.ltp": 1,
                "upstox.option_chain": 1,
            },
        )

        with (
            patch("tickertrail.cli.upstox_service.load_analytics_token", side_effect=service.UpstoxError("missing")),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            self.assertEqual(cli._print_option_chain(target, request), 3)
        self.assertIn("missing", err.getvalue())

    def test_print_chain_exact_expiry_is_validated_against_contracts(self):
        """Validate an explicit date during the same F&O contract discovery step."""
        request = service.ChainRequest("expiry", "2026-08-27", 2)
        target = cli._OptionChainTarget("SENSEX", "BSE")
        underlying = service.OptionUnderlying(
            "BSE_INDEX|SENSEX", "SENSEX", "BSE SENSEX", "BSE_INDEX"
        )
        with (
            patch("tickertrail.cli.upstox_service.load_analytics_token", return_value="token"),
            patch("tickertrail.cli.upstox_service.resolve_option_underlying", return_value=underlying),
            patch(
                "tickertrail.cli.upstox_service.fetch_underlying_quote",
                return_value=service.NiftyQuote(24590, 24500),
            ),
            patch(
                "tickertrail.cli.upstox_service.resolve_chain_contract",
                return_value=service.OptionExpiry("2026-08-27", True, 20),
            ) as mock_expiry,
            patch("tickertrail.cli.upstox_service.fetch_option_chain", return_value=_chain_rows()) as mock_chain,
            patch("tickertrail.cli._render_option_chain"),
        ):
            cli._reset_network_call_metrics()
            self.assertEqual(cli._print_option_chain(target, request), 0)
        mock_expiry.assert_called_once_with(
            "token", request, "BSE_INDEX|SENSEX", "BSE SENSEX"
        )
        mock_chain.assert_called_once_with(
            "token", "2026-08-27", instrument_key="BSE_INDEX|SENSEX"
        )
        self.assertEqual(
            cli._NETWORK_CALL_COUNTS,
            {
                "upstox.instrument_search": 1,
                "upstox.option_contract": 1,
                "upstox.ltp": 1,
                "upstox.option_chain": 1,
            },
        )

    def test_print_option_detail_uses_grouped_quote_and_fixed_four_call_budget(self):
        """Resolve one strike and batch its three range quotes in the fourth request."""
        request = service.OptionDetailRequest(24200, "next", "next")
        target = cli._OptionChainTarget("NIFTY 50", "NSE")
        underlying = service.OptionUnderlying(
            "NSE_INDEX|Nifty 50", "NIFTY", "NIFTY 50", "NSE_INDEX"
        )
        rows = _detail_rows()
        with (
            patch("tickertrail.cli.upstox_service.load_analytics_token", return_value="token"),
            patch(
                "tickertrail.cli.upstox_service.resolve_option_underlying",
                return_value=underlying,
            ) as mock_underlying,
            patch(
                "tickertrail.cli.upstox_service.resolve_chain_contract",
                return_value=service.OptionExpiry("2026-08-25", True, 65),
            ) as mock_contract,
            patch(
                "tickertrail.cli.upstox_service.fetch_option_chain", return_value=rows
            ) as mock_chain,
            patch(
                "tickertrail.cli.upstox_service.fetch_full_market_quotes",
                return_value=_detail_quotes(),
            ) as mock_quotes,
            patch("tickertrail.cli._render_option_detail") as mock_render,
        ):
            cli._reset_network_call_metrics()
            rc = cli._print_option_detail(target, request)
        self.assertEqual(rc, 0)
        mock_underlying.assert_called_once_with(
            "token", "NIFTY 50", preferred_exchange="NSE"
        )
        mock_contract.assert_called_once_with(
            "token",
            service.ChainRequest("next", "next", 10),
            "NSE_INDEX|Nifty 50",
            "NIFTY 50",
        )
        mock_chain.assert_called_once_with(
            "token", "2026-08-25", instrument_key="NSE_INDEX|Nifty 50"
        )
        mock_quotes.assert_called_once_with(
            "token",
            ["NSE_INDEX|Nifty 50", "NSE_FO|CALL24200", "NSE_FO|PUT24200"],
        )
        mock_render.assert_called_once_with(
            request,
            rows[1],
            rows,
            _detail_quotes(),
            underlying,
            65,
        )
        self.assertEqual(
            cli._NETWORK_CALL_COUNTS,
            {
                "upstox.instrument_search": 1,
                "upstox.option_contract": 1,
                "upstox.option_chain": 1,
                "upstox.market_quote": 1,
            },
        )

    def test_print_option_detail_tolerates_quote_failure_and_rejects_missing_strike(self):
        """Keep chain details usable without ranges and stop before quoting an invalid strike."""
        request = service.OptionDetailRequest(24200, "near", "near")
        target = cli._OptionChainTarget("NIFTY", "NSE")
        underlying = service.OptionUnderlying("underlying", "NIFTY", "NIFTY", "NSE_INDEX")
        rows = _detail_rows()
        with (
            patch("tickertrail.cli.upstox_service.load_analytics_token", return_value="token"),
            patch("tickertrail.cli.upstox_service.resolve_option_underlying", return_value=underlying),
            patch(
                "tickertrail.cli.upstox_service.resolve_chain_contract",
                return_value=service.OptionExpiry("2026-08-25", True, 65),
            ),
            patch("tickertrail.cli.upstox_service.fetch_option_chain", return_value=rows),
            patch(
                "tickertrail.cli.upstox_service.fetch_full_market_quotes",
                side_effect=service.UpstoxError("quote unavailable"),
            ),
            patch("tickertrail.cli._render_option_detail") as mock_render,
        ):
            self.assertEqual(cli._print_option_detail(target, request), 0)
        self.assertEqual(mock_render.call_args.args[3], {})

        missing_request = service.OptionDetailRequest(24210, "near", "near")
        with (
            patch("tickertrail.cli.upstox_service.load_analytics_token", return_value="token"),
            patch("tickertrail.cli.upstox_service.resolve_option_underlying", return_value=underlying),
            patch(
                "tickertrail.cli.upstox_service.resolve_chain_contract",
                return_value=service.OptionExpiry("2026-08-25", True, 65),
            ),
            patch("tickertrail.cli.upstox_service.fetch_option_chain", return_value=rows),
            patch("tickertrail.cli.upstox_service.fetch_full_market_quotes") as mock_quotes,
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            self.assertEqual(cli._print_option_detail(target, missing_request), 3)
        mock_quotes.assert_not_called()
        self.assertIn("Nearby listed strikes", err.getvalue())

        with (
            patch(
                "tickertrail.cli.upstox_service.load_analytics_token",
                side_effect=service.UpstoxError("missing token"),
            ),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            self.assertEqual(cli._print_option_detail(target, request), 3)
        self.assertIn("missing token", err.getvalue())

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_company_fundamentals", return_value=0)
    @patch("tickertrail.cli._print_quote", return_value=0)
    def test_repl_routes_stock_fundmentals_and_alias_without_qualifiers(
        self, _mock_quote, mock_fundamentals, _mock_history
    ):
        """Dispatch only the exact canonical and alias forms from a stock prompt."""
        with (
            patch(
                "builtins.input",
                side_effect=["fundmentals", "funda", "funda quarterly", "fundmentals x", "exit"],
            ),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = cli._run_repl(
                "reliance", "RELIANCE.NS", {"regularMarketPrice": 1.0}, 100, 22
            )
        self.assertEqual(rc, 0)
        self.assertEqual([call.args for call in mock_fundamentals.call_args_list], [("RELIANCE.NS",)] * 2)
        self.assertEqual(err.getvalue().count("Usage: fundmentals"), 2)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_company_fundamentals", return_value=0)
    @patch("tickertrail.cli._print_quote", return_value=0)
    def test_repl_rejects_fundmentals_outside_stock_context(
        self, _mock_quote, mock_fundamentals, _mock_history
    ):
        """Reject root, index, and watchlist execution without making API calls."""
        with (
            patch("builtins.input", side_effect=["fundmentals", "exit"]),
            patch("sys.stderr", new_callable=io.StringIO) as root_err,
        ):
            self.assertEqual(cli._run_repl(None, None, None, 100, 22), 0)
        self.assertIn("requires an active stock", root_err.getvalue())

        with (
            patch("builtins.input", side_effect=["funda", "exit"]),
            patch("sys.stderr", new_callable=io.StringIO) as index_err,
        ):
            self.assertEqual(
                cli._run_repl("nifty", "^NSEI", {"regularMarketPrice": 1.0}, 100, 22),
                0,
            )
        self.assertIn("requires an active stock", index_err.getvalue())

        with (
            patch("tickertrail.cli._watchlist_symbols", return_value=["RELIANCE.NS"]),
            patch("builtins.input", side_effect=["watchlist open core", "funda", "exit"]),
            patch("sys.stderr", new_callable=io.StringIO) as watchlist_err,
        ):
            self.assertEqual(cli._run_repl(None, None, None, 100, 22), 0)
        self.assertIn("unavailable in watchlist mode", watchlist_err.getvalue())
        mock_fundamentals.assert_not_called()

    def test_print_company_fundamentals_tracks_requests_and_handles_errors(self):
        """Track injected Upstox requests and convert safe service failures to status 3."""
        snapshot = object()

        def fake_fetch(token, query, *, preferred_exchange, request_json_fn):
            """Exercise the CLI's tracked request wrapper before returning a sentinel."""
            self.assertEqual((token, query, preferred_exchange), ("token", "RELIANCE", "NSE"))
            request_json_fn("/v2/fundamentals/INE/key-ratios", {}, token)
            return snapshot

        with (
            patch("tickertrail.cli.upstox_service.load_analytics_token", return_value="token"),
            patch("tickertrail.cli.upstox_service.request_json", return_value={}) as request,
            patch(
                "tickertrail.cli.fundamentals.fetch_company_fundamentals",
                side_effect=fake_fetch,
            ),
            patch("tickertrail.cli.fundamentals.render_company_fundamentals") as render,
        ):
            cli._reset_network_call_metrics()
            self.assertEqual(cli._print_company_fundamentals("RELIANCE.NS"), 0)
        request.assert_called_once_with("/v2/fundamentals/INE/key-ratios", {}, "token")
        render.assert_called_once_with(snapshot, cli._style_text)
        self.assertEqual(cli._NETWORK_CALL_COUNTS, {"upstox.key_ratios": 1})

        with (
            patch(
                "tickertrail.cli.upstox_service.load_analytics_token",
                side_effect=service.UpstoxError("missing token"),
            ),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            self.assertEqual(cli._print_company_fundamentals("RELIANCE.NS"), 3)
        self.assertIn("missing token", err.getvalue())


if __name__ == "__main__":
    unittest.main()
