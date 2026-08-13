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

    def test_chain_parser_resolves_nifty_context_and_root_override(self):
        """Accept contextual and one-shot NIFTY commands while rejecting other contexts."""
        contextual, error = cli._parse_nifty_chain_command(["next", "strikes", "3"], "^NSEI")
        self.assertIsNone(error)
        self.assertEqual(contextual, service.ChainRequest("next", "next", 3))
        one_shot, error = cli._parse_nifty_chain_command(["nifty", "month"], None)
        self.assertIsNone(error)
        self.assertEqual(one_shot, service.ChainRequest("month", "month", 10))
        rejected, error = cli._parse_nifty_chain_command([], "AAPL")
        self.assertIsNone(rejected)
        self.assertIn("NIFTY only", error or "")

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_nifty_option_chain", return_value=0)
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
            [call.args[0] for call in mock_chain.call_args_list],
            [
                service.ChainRequest("near", "near", 10),
                service.ChainRequest("next", "next", 3),
                service.ChainRequest("far", "far", 10),
            ],
        )
        self.assertIn("Command: chain", out.getvalue())

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_nifty_option_chain", return_value=0)
    def test_repl_routes_root_chain_nifty_and_rejects_non_nifty(self, mock_chain, _mock_hist):
        """Support a root one-shot command and keep failures network-free."""
        with (
            patch("builtins.input", side_effect=["chain", "chain nifty month", "exit"]),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = cli._run_repl(None, None, None, 100, 22)
        self.assertEqual(rc, 0)
        mock_chain.assert_called_once_with(service.ChainRequest("month", "month", 10))
        self.assertIn("NIFTY only", err.getvalue())

    def test_render_chain_has_descending_bold_spine_headers_and_atm_row(self):
        """Render bold headers/spine/ATM with independent option-side colours."""
        with (
            patch("tickertrail.cli._supports_color", return_value=True),
            patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            cli._render_nifty_option_chain(
                service.ChainRequest("near", "near", 2),
                _chain_rows(),
                service.NiftyQuote(24590.0, 24460.0),
            )
        rendered = out.getvalue()
        plain = cli._ANSI_ESCAPE_RE.sub("", rendered)
        self.assertIn("NIFTY 50  24,590.00  +130.00 (+0.53%) ↑", plain)
        self.assertIn("Expiry 20-Aug-2026", plain)
        self.assertIn("Delta         LTP (Today) │", plain)
        self.assertIn("│ LTP (Today)           Delta", plain)
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
            cli._render_nifty_option_chain(service.ChainRequest("far", "far", 1), rows, None)
        self.assertIn("24,590.00  n/a", out.getvalue())
        self.assertIn("n/a", out.getvalue())

    def test_chain_expiry_label_preserves_non_iso_values(self):
        """Keep an unexpected expiry readable instead of failing rendering."""
        self.assertEqual(cli._format_chain_expiry_label("n/a"), "n/a")

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
        with self.assertRaisesRegex(service.UpstoxError, "no current NIFTY value"):
            cli._render_nifty_option_chain(
                service.ChainRequest("near", "near", 10),
                missing_spot_rows,
                None,
            )

    def test_print_chain_fetches_quote_and_chain_with_spot_fallback(self):
        """Track both Upstox calls and tolerate a failed header quote."""
        request = service.ChainRequest("near", "near", 2)
        with (
            patch("tickertrail.cli.upstox_service.load_analytics_token", return_value="token"),
            patch("tickertrail.cli.upstox_service.fetch_nifty_quote", side_effect=service.UpstoxError("quote down")),
            patch("tickertrail.cli.upstox_service.resolve_chain_expiry", return_value="2026-08-18") as mock_expiry,
            patch("tickertrail.cli.upstox_service.fetch_option_chain", return_value=_chain_rows()) as mock_chain,
            patch("tickertrail.cli._render_nifty_option_chain") as mock_render,
        ):
            cli._reset_network_call_metrics()
            rc = cli._print_nifty_option_chain(request)
        self.assertEqual(rc, 0)
        mock_expiry.assert_called_once_with("token", request)
        mock_chain.assert_called_once_with("token", "2026-08-18")
        mock_render.assert_called_once_with(request, unittest.mock.ANY, None)
        self.assertEqual(
            cli._NETWORK_CALL_COUNTS,
            {"upstox.ltp": 1, "upstox.option_contract": 1, "upstox.option_chain": 1},
        )

        with (
            patch("tickertrail.cli.upstox_service.load_analytics_token", side_effect=service.UpstoxError("missing")),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            self.assertEqual(cli._print_nifty_option_chain(request), 3)
        self.assertIn("missing", err.getvalue())

    def test_print_chain_exact_expiry_skips_contract_lookup(self):
        """Use an explicit date directly without fetching the contract calendar."""
        request = service.ChainRequest("expiry", "2026-08-27", 2)
        with (
            patch("tickertrail.cli.upstox_service.load_analytics_token", return_value="token"),
            patch(
                "tickertrail.cli.upstox_service.fetch_nifty_quote",
                return_value=service.NiftyQuote(24590, 24500),
            ),
            patch("tickertrail.cli.upstox_service.resolve_chain_expiry") as mock_expiry,
            patch("tickertrail.cli.upstox_service.fetch_option_chain", return_value=_chain_rows()) as mock_chain,
            patch("tickertrail.cli._render_nifty_option_chain"),
        ):
            cli._reset_network_call_metrics()
            self.assertEqual(cli._print_nifty_option_chain(request), 0)
        mock_expiry.assert_not_called()
        mock_chain.assert_called_once_with("token", "2026-08-27")
        self.assertEqual(cli._NETWORK_CALL_COUNTS, {"upstox.ltp": 1, "upstox.option_chain": 1})


if __name__ == "__main__":
    unittest.main()
