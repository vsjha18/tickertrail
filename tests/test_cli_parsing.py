import unittest

from tickertrail.cli import (
    _outperformance_pct,
    _parse_compare_command_args,
    _parse_intraday_command_args,
    _parse_swing_command_args,
    _validate_period_interval,
)


class SwingParserTests(unittest.TestCase):
    def test_table_dash_period(self) -> None:
        parsed, err = _parse_swing_command_args(["-", "2y"], command_name="t")
        self.assertIsNone(err)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.period_token, "2y")
        self.assertIsNone(parsed.interval_override)
        self.assertIsNone(parsed.benchmark_input)

    def test_table_dash_period_agg(self) -> None:
        parsed, err = _parse_swing_command_args(["-", "2y", "mo"], command_name="t")
        self.assertIsNone(err)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.period_token, "2y")
        self.assertEqual(parsed.interval_override, "1mo")

    def test_chart_benchmark_dash_period_agg(self) -> None:
        parsed, err = _parse_swing_command_args(["nifty", "-", "3mo", "w"], command_name="c")
        self.assertIsNone(err)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.benchmark_input, "nifty")
        self.assertEqual(parsed.period_token, "3mo")
        self.assertEqual(parsed.interval_override, "1wk")

    def test_chart_dash_agg_only(self) -> None:
        parsed, err = _parse_swing_command_args(["-", "w"], command_name="c")
        self.assertIsNone(err)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.period_token, "6mo")
        self.assertEqual(parsed.interval_override, "1wk")
        self.assertIsNone(parsed.benchmark_input)

    def test_chart_benchmark_dash_agg_only(self) -> None:
        parsed, err = _parse_swing_command_args(["nifty", "-", "w"], command_name="c")
        self.assertIsNone(err)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.period_token, "6mo")
        self.assertEqual(parsed.interval_override, "1wk")
        self.assertEqual(parsed.benchmark_input, "nifty")

    def test_legacy_benchmark_only_retained(self) -> None:
        parsed, err = _parse_swing_command_args(["nifty"], command_name="t")
        self.assertIsNone(err)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.benchmark_input, "nifty")
        self.assertEqual(parsed.period_token, "6mo")

    def test_invalid_period_unit_m_is_rejected(self) -> None:
        parsed, err = _parse_swing_command_args(["-", "3m"], command_name="t")
        self.assertIsNone(parsed)
        self.assertIsNotNone(err)
        assert err is not None
        self.assertIn("Unsupported period/aggregation token", err)


class IntradayParserTests(unittest.TestCase):
    def test_intraday_interval(self) -> None:
        parsed, err = _parse_intraday_command_args(["15m"])
        self.assertIsNone(err)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.interval, "15m")
        self.assertIsNone(parsed.benchmark_input)

    def test_intraday_benchmark_interval(self) -> None:
        parsed, err = _parse_intraday_command_args(["nifty", "5m"])
        self.assertIsNone(err)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.benchmark_input, "nifty")
        self.assertEqual(parsed.interval, "5m")

    def test_intraday_extended_intervals(self) -> None:
        parsed_30m, err_30m = _parse_intraday_command_args(["30m"])
        self.assertIsNone(err_30m)
        self.assertIsNotNone(parsed_30m)
        assert parsed_30m is not None
        self.assertEqual(parsed_30m.interval, "30m")

        parsed_1hr, err_1hr = _parse_intraday_command_args(["1hr"])
        self.assertIsNone(err_1hr)
        self.assertIsNotNone(parsed_1hr)
        assert parsed_1hr is not None
        self.assertEqual(parsed_1hr.interval, "1h")

    def test_intraday_invalid_interval(self) -> None:
        parsed, err = _parse_intraday_command_args(["nifty", "mo"])
        self.assertIsNone(parsed)
        self.assertIsNotNone(err)

    def test_intraday_dash_interval(self) -> None:
        parsed, err = _parse_intraday_command_args(["-", "30m"], command_name="tt")
        self.assertIsNone(err)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.interval, "30m")
        self.assertIsNone(parsed.benchmark_input)

    def test_intraday_benchmark_dash_interval(self) -> None:
        parsed, err = _parse_intraday_command_args(["bank", "-", "1hr"], command_name="tt")
        self.assertIsNone(err)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.interval, "1h")
        self.assertEqual(parsed.benchmark_input, "bank")

    def test_intraday_dash_rejects_period_token(self) -> None:
        parsed, err = _parse_intraday_command_args(["-", "2y"], command_name="tt")
        self.assertIsNone(parsed)
        self.assertIsNotNone(err)


class CompatibilityValidatorTests(unittest.TestCase):
    def test_intraday_limit_for_1m(self) -> None:
        err = _validate_period_interval("3mo", "1m")
        self.assertIsNotNone(err)
        assert err is not None
        self.assertIn("supports up to 7d", err)

    def test_intraday_limit_for_5m(self) -> None:
        err = _validate_period_interval("6mo", "5m")
        self.assertIsNotNone(err)
        assert err is not None
        self.assertIn("supports up to 60d", err)

    def test_valid_weekly_aggregation(self) -> None:
        err = _validate_period_interval("2y", "1wk")
        self.assertIsNone(err)


class OutperformanceMathTests(unittest.TestCase):
    def test_outperformance_positive(self) -> None:
        self.assertAlmostEqual(_outperformance_pct(120.0, 100.0), 20.0, places=6)

    def test_outperformance_negative(self) -> None:
        self.assertAlmostEqual(_outperformance_pct(90.0, 100.0), -10.0, places=6)

    def test_outperformance_zero_benchmark_guard(self) -> None:
        self.assertEqual(_outperformance_pct(100.0, 0.0), 0.0)


class AdditionalParserBehaviorTests(unittest.TestCase):
    def test_parse_compare_with_period_and_agg(self) -> None:
        parsed, err = _parse_compare_command_args(["nifty", "goldbees", "hdfcbank", "3y", "w"])
        self.assertIsNone(err)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.symbols, ("nifty", "goldbees", "hdfcbank"))
        self.assertEqual(parsed.period_token, "3y")
        self.assertEqual(parsed.interval_override, "1wk")

    def test_parse_compare_without_period_uses_default_6mo(self) -> None:
        parsed, err = _parse_compare_command_args(["nifty", "goldbees"])
        self.assertIsNone(err)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.period_token, "6mo")
        self.assertIsNone(parsed.interval_override)

    def test_parse_compare_accepts_month_shorthand(self) -> None:
        parsed, err = _parse_compare_command_args(["nifty", "goldbees", "6m"])
        self.assertIsNone(err)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.period_token, "6mo")

    def test_parse_compare_requires_two_distinct_symbols(self) -> None:
        parsed, err = _parse_compare_command_args(["nifty", "nifty", "1y"])
        self.assertIsNone(parsed)
        self.assertIsNotNone(err)
        assert err is not None
        self.assertIn("distinct symbols", err)

    def test_parse_swing_invalid_dash_arity(self) -> None:
        parsed, err = _parse_swing_command_args(["-"], command_name="t")
        self.assertIsNone(parsed)
        self.assertIsNotNone(err)
        assert err is not None
        self.assertIn("Usage: t - <period|agg> [agg]", err)

    def test_parse_swing_invalid_agg_token_in_dash_form(self) -> None:
        parsed, err = _parse_swing_command_args(["-", "2y", "2w"], command_name="c")
        self.assertIsNone(parsed)
        self.assertIsNotNone(err)
        assert err is not None
        self.assertIn("Unsupported aggregation token", err)

    def test_parse_swing_invalid_benchmark_dash_arity(self) -> None:
        parsed, err = _parse_swing_command_args(["nifty", "-", "2y", "mo", "x"], command_name="c")
        self.assertIsNone(parsed)
        self.assertIsNotNone(err)
        assert err is not None
        self.assertIn("Usage: c <benchmark> - <period|agg> [agg]", err)

    def test_parse_swing_invalid_benchmark_dash_period(self) -> None:
        parsed, err = _parse_swing_command_args(["nifty", "-", "3m"], command_name="t")
        self.assertIsNone(parsed)
        self.assertIsNotNone(err)
        assert err is not None
        self.assertIn("Unsupported period/aggregation token", err)

    def test_parse_swing_two_token_usage_error(self) -> None:
        parsed, err = _parse_swing_command_args(["nifty", "oops"], command_name="t")
        self.assertIsNone(parsed)
        self.assertIsNotNone(err)
        assert err is not None
        self.assertIn("Usage:", err)

    def test_parse_intraday_too_many_args(self) -> None:
        parsed, err = _parse_intraday_command_args(["nifty", "5m", "x"])
        self.assertIsNone(parsed)
        self.assertIsNotNone(err)
        assert err is not None
        self.assertIn("Usage:", err)

    def test_validate_period_interval_max_intraday_guard(self) -> None:
        err = _validate_period_interval("max", "1m")
        self.assertIsNotNone(err)
        assert err is not None
        self.assertIn("not supported with period 'max'", err)


if __name__ == "__main__":
    unittest.main()
