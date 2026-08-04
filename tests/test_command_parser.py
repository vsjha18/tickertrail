import unittest

from tickertrail import command_parser


class CommandParserTests(unittest.TestCase):
    """Exercise the extracted command grammar without CLI or network setup."""

    def test_swing_command_forms(self) -> None:
        """Parse defaults, context-preserving overrides, and benchmark forms."""
        default, default_error = command_parser.parse_swing_command_args([], "t")
        override, override_error = command_parser.parse_swing_command_args(["-", "2y", "mo"], "t")
        benchmark, benchmark_error = command_parser.parse_swing_command_args(["nifty", "3mo", "w"], "t")

        self.assertEqual(default, command_parser.SwingCommand())
        self.assertIsNone(default_error)
        self.assertEqual(override, command_parser.SwingCommand("2y", "1mo"))
        self.assertIsNone(override_error)
        self.assertEqual(benchmark, command_parser.SwingCommand("3mo", "1wk", "nifty"))
        self.assertIsNone(benchmark_error)

    def test_intraday_command_forms(self) -> None:
        """Normalize interval aliases and retain optional benchmark input."""
        interval, interval_error = command_parser.parse_intraday_command_args(["1hr"])
        benchmark, benchmark_error = command_parser.parse_intraday_command_args(["bank", "-", "30m"], "tt")

        self.assertEqual(interval, command_parser.IntradayCommand("1h"))
        self.assertIsNone(interval_error)
        self.assertEqual(benchmark, command_parser.IntradayCommand("30m", "bank"))
        self.assertIsNone(benchmark_error)

    def test_compare_command_forms(self) -> None:
        """Parse symbol tails and reject duplicate-only comparisons."""
        parsed, error = command_parser.parse_compare_command_args(["nifty", "goldbees", "hdfcbank", "3y", "w"])
        duplicate, duplicate_error = command_parser.parse_compare_command_args(["nifty", "nifty"])

        self.assertEqual(
            parsed,
            command_parser.CompareCommand(("nifty", "goldbees", "hdfcbank"), "3y", "1wk"),
        )
        self.assertIsNone(error)
        self.assertIsNone(duplicate)
        self.assertIn("distinct symbols", duplicate_error or "")

    def test_analytics_command_forms(self) -> None:
        """Parse analytics periods, explicit scope, and relative benchmarks."""
        self.assertTrue(command_parser.is_analytics_period_token("11mo"))
        self.assertFalse(command_parser.is_analytics_period_token("12mo"))
        self.assertEqual(command_parser.parse_moves_period(["2y"]), ("2y", None))
        self.assertEqual(
            command_parser.parse_scope_override_with_period(
                ["on", "infy", "tcs", "3mo"],
                command_name="moves",
                period_tokens={"1mo", "3mo"},
                default_period="1mo",
            ),
            (["infy", "tcs"], "3mo", None),
        )
        self.assertEqual(
            command_parser.parse_relret_args(["on", "infy", "tcs", "6mo", "vs", "it"]),
            (["infy", "tcs"], "6mo", "it", None),
        )
        self.assertEqual(command_parser.parse_corr_period(["7d"]), ("7d", None))

    def test_invalid_grammar_guardrails(self) -> None:
        """Reject malformed dash, scope, comparison, and relative-return forms."""
        invalid_calls = (
            command_parser.parse_swing_command_args(["-", "bad", "w"], "t"),
            command_parser.parse_swing_command_args(["nifty", "-", "bad", "w"], "t"),
            command_parser.parse_intraday_command_args(["-"], "cc"),
            command_parser.parse_intraday_command_args(["nifty", "-"], "tt"),
            command_parser.parse_compare_command_args(["nifty"]),
        )
        for parsed, error in invalid_calls:
            self.assertIsNone(parsed)
            self.assertIsNotNone(error)

        benchmark_period, benchmark_period_error = command_parser.parse_swing_command_args(
            ["nifty", "-", "2y"],
            "t",
        )
        self.assertEqual(benchmark_period, command_parser.SwingCommand("2y", benchmark_input="nifty"))
        self.assertIsNone(benchmark_period_error)
        self.assertFalse(command_parser.is_analytics_period_token("bad"))

        scope_cases = (
            command_parser.parse_scope_override_with_period(
                ["3mo", "extra"],
                command_name="moves",
                period_tokens={"1mo", "3mo"},
                default_period="1mo",
            ),
            command_parser.parse_scope_override_with_period(
                ["on"],
                command_name="moves",
                period_tokens={"1mo", "3mo"},
                default_period="1mo",
            ),
        )
        for symbols, period, error in scope_cases:
            self.assertIsNone(symbols)
            self.assertIsNone(period)
            self.assertIsNotNone(error)

        relret_cases = (
            ["vs", "it", "vs", "nifty"],
            ["vs", "it", "12mo"],
            ["on", "infy", "12mo"],
            ["infy", "tcs"],
        )
        for args in relret_cases:
            symbols, period, benchmark, error = command_parser.parse_relret_args(args)
            self.assertIsNone(symbols)
            self.assertIsNone(period)
            self.assertIsNone(benchmark)
            self.assertIsNotNone(error)


if __name__ == "__main__":
    unittest.main()
