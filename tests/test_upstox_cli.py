from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tickertrail import cli
from tickertrail import upstox_service as service


def _side(ltp: float, close: float, delta: float) -> service.OptionSide:
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
    )


def _chain_rows() -> list[service.OptionChainRow]:
    """Build a small chain around a 24,600 ATM strike."""
    return [
        service.OptionChainRow(float(strike), "2026-08-20", 24590.0, _side(120 + offset, 110, 0.52), _side(120 - offset, 125, -0.48))
        for offset, strike in enumerate(range(24450, 24751, 50))
    ]


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
            )
        rendered = out.getvalue()
        plain = cli._ANSI_ESCAPE_RE.sub("", rendered)
        self.assertIn("NIFTY 50  24,590.00  +130.00 (+0.53%) ↑", plain)
        self.assertIn("Expiry 20-Aug-2026", plain)
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
                service.ChainRequest("far", "far", 1), rows, None, "Nifty 50"
            )
        self.assertIn("24,590.00  n/a", out.getvalue())
        self.assertIn("n/a", out.getvalue())

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
            patch("tickertrail.cli.upstox_service.resolve_chain_expiry", return_value="2026-08-18") as mock_expiry,
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
        mock_render.assert_called_once_with(request, unittest.mock.ANY, None, "RELIANCE")
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
            patch("tickertrail.cli.upstox_service.resolve_chain_expiry", return_value="2026-08-27") as mock_expiry,
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


if __name__ == "__main__":
    unittest.main()
