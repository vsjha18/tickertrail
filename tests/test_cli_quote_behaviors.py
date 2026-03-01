import unittest
from unittest.mock import patch

from tickertrail.cli import (
    _parse_intraday_command_args,
    _parse_swing_command_args,
    _run_repl,
    _validate_period_interval,
)


class ParserNoNetworkGuardTests(unittest.TestCase):
    @patch("tickertrail.cli.yf.Ticker", side_effect=AssertionError("network call not allowed"))
    @patch("tickertrail.cli.yf.download", side_effect=AssertionError("network call not allowed"))
    def test_parser_and_validator_are_pure(self, _mock_download, _mock_ticker) -> None:
        parsed, err = _parse_swing_command_args(["nifty", "3mo", "w"], command_name="t")
        self.assertIsNone(err)
        self.assertIsNotNone(parsed)

        parsed_cc, err_cc = _parse_intraday_command_args(["banknifty", "5m"])
        self.assertIsNone(err_cc)
        self.assertIsNotNone(parsed_cc)

        err_val = _validate_period_interval("2y", "1wk")
        self.assertIsNone(err_val)


class ReplNoNetworkBehaviorTests(unittest.TestCase):
    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._resolve_symbol_with_fallback", side_effect=AssertionError("symbol resolution must not run"))
    def test_cls_does_not_trigger_symbol_resolution(self, _mock_resolve, _mock_history) -> None:
        with patch("builtins.input", side_effect=["cls", "exit"]):
            rc = _run_repl(
                start_input_symbol=None,
                start_resolved_symbol=None,
                start_info=None,
                width=100,
                height=22,
            )
        self.assertEqual(rc, 0)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=0)
    @patch("tickertrail.cli._resolve_benchmark_for_table", return_value=("^NSEI", "NIFTY 50", None))
    @patch("tickertrail.cli._render_rebased_table", return_value=0)
    def test_tt_default_uses_intraday_defaults(
        self,
        mock_render_table,
        _mock_resolve_bench,
        _mock_print_quote,
        _mock_history,
    ) -> None:
        with patch("builtins.input", side_effect=["tt", "exit"]):
            rc = _run_repl(
                start_input_symbol="BEL",
                start_resolved_symbol="BEL.NS",
                start_info={"regularMarketPrice": 100.0, "regularMarketPreviousClose": 99.0},
                width=100,
                height=22,
            )
        self.assertEqual(rc, 0)
        self.assertEqual(mock_render_table.call_count, 1)
        kwargs = mock_render_table.call_args.kwargs
        self.assertEqual(kwargs["period_token"], "1d")
        self.assertEqual(kwargs["interval_override"], "5m")

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=0)
    @patch("tickertrail.cli._resolve_benchmark_for_table", return_value=("SBIN.NS", "STATE BANK OF INDIA", None))
    @patch("tickertrail.cli._render_rebased_table", return_value=0)
    def test_tt_symbol_only_keeps_intraday_and_sets_benchmark(
        self,
        mock_render_table,
        mock_resolve_bench,
        _mock_print_quote,
        _mock_history,
    ) -> None:
        with patch("builtins.input", side_effect=["tt sbin", "exit"]):
            rc = _run_repl(
                start_input_symbol="HDFCBANK",
                start_resolved_symbol="HDFCBANK.NS",
                start_info={"regularMarketPrice": 100.0, "regularMarketPreviousClose": 99.0},
                width=100,
                height=22,
            )
        self.assertEqual(rc, 0)
        self.assertEqual(mock_render_table.call_count, 1)
        self.assertEqual(mock_resolve_bench.call_args.kwargs["benchmark_input"], "sbin")
        kwargs = mock_render_table.call_args.kwargs
        self.assertEqual(kwargs["period_token"], "1d")
        self.assertEqual(kwargs["interval_override"], "5m")

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=0)
    @patch("tickertrail.cli._resolve_benchmark_for_table", return_value=("^NSEI", "NIFTY 50", None))
    @patch("tickertrail.cli._render_rebased_table", return_value=0)
    def test_tt_dash_allows_explicit_swing_period(
        self,
        mock_render_table,
        _mock_resolve_bench,
        _mock_print_quote,
        _mock_history,
    ) -> None:
        with patch("builtins.input", side_effect=["tt - 2y mo", "exit"]):
            rc = _run_repl(
                start_input_symbol="BEL",
                start_resolved_symbol="BEL.NS",
                start_info={"regularMarketPrice": 100.0, "regularMarketPreviousClose": 99.0},
                width=100,
                height=22,
            )
        self.assertEqual(rc, 0)
        kwargs = mock_render_table.call_args.kwargs
        self.assertEqual(kwargs["period_token"], "2y")
        self.assertEqual(kwargs["interval_override"], "1mo")

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._get_quote_payload", side_effect=AssertionError("network call not expected"))
    def test_reload_without_active_symbol_does_not_fetch(self, _mock_get_quote, _mock_history) -> None:
        with patch("builtins.input", side_effect=["reload", "exit"]):
            rc = _run_repl(
                start_input_symbol=None,
                start_resolved_symbol=None,
                start_info=None,
                width=100,
                height=22,
            )
        self.assertEqual(rc, 0)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=0)
    @patch("tickertrail.cli._resolve_benchmark_for_table", return_value=("^NSEI", "NIFTY 50", None))
    @patch("tickertrail.cli._render_rebased_table", return_value=0)
    @patch("tickertrail.cli._has_quote_data", return_value=True)
    @patch("tickertrail.cli._get_quote_payload", return_value={"regularMarketPrice": 101.0, "regularMarketPreviousClose": 100.0})
    def test_r_replays_last_table_view(
        self,
        _mock_get_quote,
        _mock_has_data,
        mock_render_table,
        _mock_resolve_bench,
        _mock_print_quote,
        _mock_history,
    ) -> None:
        with patch("builtins.input", side_effect=["t", "r", "exit"]):
            rc = _run_repl(
                start_input_symbol="BEL",
                start_resolved_symbol="BEL.NS",
                start_info={"regularMarketPrice": 100.0, "regularMarketPreviousClose": 99.0},
                width=100,
                height=22,
            )
        self.assertEqual(rc, 0)
        self.assertEqual(mock_render_table.call_count, 2)


if __name__ == "__main__":
    unittest.main()
