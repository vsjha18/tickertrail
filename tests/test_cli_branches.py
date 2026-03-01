import datetime as dt
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

import tickertrail.cli as cli


class BranchHelperTests(unittest.TestCase):
    def test_supports_color_paths(self):
        with patch("sys.stdout.isatty", return_value=True), patch.dict("os.environ", {}, clear=True):
            self.assertTrue(cli._supports_color())
        with patch("sys.stdout.isatty", return_value=False):
            self.assertFalse(cli._supports_color())
        with patch("sys.stdout.isatty", return_value=True), patch.dict("os.environ", {"NO_COLOR": "1"}, clear=False):
            self.assertFalse(cli._supports_color())

    def test_colorize_unknown_color(self):
        with patch("tickertrail.cli._supports_color", return_value=True):
            self.assertEqual(cli._colorize("x", "unknown"), "x")

    def test_index_alias_target_and_known_index_symbol_helpers(self):
        self.assertTrue(cli._is_known_index_symbol("^CNXIT"))
        self.assertTrue(cli._is_known_index_symbol("NIFTY_FIN_SERVICE.NS"))
        self.assertFalse(cli._is_known_index_symbol("ITC.NS"))
        self.assertEqual(cli._index_alias_target("it"), "^CNXIT")
        self.assertEqual(cli._index_alias_target("mnc"), "^CNXMNC")
        self.assertEqual(cli._index_alias_target("metals"), "^CNXMETAL")
        self.assertIsNone(cli._index_alias_target("itc"))
        self.assertEqual(cli._index_label_for_symbol("^CNXIT"), "NIFTY IT")
        self.assertEqual(cli._index_label_for_symbol("^UNKNOWN"), "^UNKNOWN")

    @patch("tickertrail.cli._batch_index_snapshots", return_value={"^CNXIT": {"regularMarketPrice": None, "regularMarketPreviousClose": None}})
    def test_index_quote_fallback_payload_none_when_snapshot_has_no_price_anchor(self, _mock_batch):
        self.assertIsNone(cli._index_quote_fallback_payload("^CNXIT"))

    @patch("tickertrail.cli._batch_index_snapshots")
    def test_index_quote_fallback_payload_uses_candidates_and_builds_quote_like_payload(self, mock_batch):
        mock_batch.return_value = {
            "^CNXMIDCAP": {"regularMarketPrice": None, "regularMarketPreviousClose": None},
            "^NSEMDCP100": {
                "regularMarketPrice": 123.4,
                "regularMarketPreviousClose": 120.0,
                "regularMarketDayLow": 119.0,
                "regularMarketDayHigh": 125.0,
            },
        }
        payload = cli._index_quote_fallback_payload("^CNXMIDCAP")
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["shortName"], "NIFTY MIDCAP 100")
        self.assertEqual(payload["regularMarketPrice"], 123.4)
        self.assertEqual(payload["regularMarketPreviousClose"], 120.0)

    def test_index_quote_fallback_payload_rejects_empty_symbol(self):
        self.assertIsNone(cli._index_quote_fallback_payload("   "))

    def test_progress_scope_and_network_blip(self):
        with (
            patch("tickertrail.cli._progress_enabled", return_value=True),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            cli._reset_network_call_metrics()
            cli._progress_start("Resolving batch")
            cli._track_network_call("yfinance.download")
            cli._progress_stop()
            txt = err.getvalue()
        self.assertIn("#", txt)
        self.assertTrue(txt.endswith("\n"))
        self.assertFalse(cli._PROGRESS_STATE["active"])

    @patch("tickertrail.cli.time.sleep")
    @patch("tickertrail.cli.random.uniform", return_value=0.015)
    def test_ticker_fallback_pause_includes_jitter_and_backoff(self, mock_uniform, mock_sleep):
        with patch("tickertrail.cli._load_runtime_config", return_value={
            "ticker_fallback_jitter_min_s": 0.01,
            "ticker_fallback_jitter_max_s": 0.02,
            "ticker_fallback_backoff_step_s": 0.050,
            "ticker_fallback_backoff_max_s": 0.200,
        }):
            cli._ticker_fallback_pause(0)
            cli._ticker_fallback_pause(10)
        self.assertEqual(mock_uniform.call_count, 2)
        self.assertEqual(mock_sleep.call_args_list[0].args[0], 0.015)
        self.assertEqual(mock_sleep.call_args_list[1].args[0], 0.115)

    def test_load_runtime_config_from_json_file(self):
        old_path = cli._CLI_CONF_JSON
        old_cache = cli._RUNTIME_CONFIG_CACHE
        try:
            with tempfile.TemporaryDirectory() as td:
                conf_path = Path(td) / "conf.json"
                conf_path.write_text(
                    "{"
                    "\"ticker_fallback_jitter_min\": \"20ms\","
                    "\"ticker_fallback_jitter_max\": \"10ms\","
                    "\"ticker_fallback_backoff_step\": \"30ms\","
                    "\"ticker_fallback_backoff_max\": \"150ms\""
                    "}",
                    encoding="utf-8",
                )
                cli._CLI_CONF_JSON = conf_path
                cli._RUNTIME_CONFIG_CACHE = None
                cfg = cli._load_runtime_config()
                self.assertEqual(cfg["ticker_fallback_jitter_min_s"], 0.02)
                # max is normalized to min when config is inverted
                self.assertEqual(cfg["ticker_fallback_jitter_max_s"], 0.02)
                self.assertEqual(cfg["ticker_fallback_backoff_step_s"], 0.03)
                self.assertEqual(cfg["ticker_fallback_backoff_max_s"], 0.15)
        finally:
            cli._CLI_CONF_JSON = old_path
            cli._RUNTIME_CONFIG_CACHE = old_cache

    def test_load_runtime_config_legacy_keys_backward_compatible(self):
        old_path = cli._CLI_CONF_JSON
        old_cache = cli._RUNTIME_CONFIG_CACHE
        try:
            with tempfile.TemporaryDirectory() as td:
                conf_path = Path(td) / "conf.json"
                conf_path.write_text(
                    "{"
                    "\"ticker_fallback_jitter_min_s\": \"15ms\","
                    "\"ticker_fallback_jitter_max_s\": \"25ms\","
                    "\"ticker_fallback_backoff_step_s\": \"40ms\","
                    "\"ticker_fallback_backoff_max_s\": \"120ms\""
                    "}",
                    encoding="utf-8",
                )
                cli._CLI_CONF_JSON = conf_path
                cli._RUNTIME_CONFIG_CACHE = None
                cfg = cli._load_runtime_config()
                self.assertEqual(cfg["ticker_fallback_jitter_min_s"], 0.015)
                self.assertEqual(cfg["ticker_fallback_jitter_max_s"], 0.025)
                self.assertEqual(cfg["ticker_fallback_backoff_step_s"], 0.04)
                self.assertEqual(cfg["ticker_fallback_backoff_max_s"], 0.12)
        finally:
            cli._CLI_CONF_JSON = old_path
            cli._RUNTIME_CONFIG_CACHE = old_cache

    def test_read_conf_duration_seconds_formats(self):
        payload = {
            "ms": "25ms",
            "s": "0.4s",
            "num": 0.2,
            "neg": "-1ms",
            "bad": "nope",
        }
        self.assertEqual(cli._read_conf_duration_seconds(payload, "ms"), 0.025)
        self.assertEqual(cli._read_conf_duration_seconds(payload, "s"), 0.4)
        self.assertEqual(cli._read_conf_duration_seconds(payload, "num"), 0.2)
        self.assertEqual(cli._read_conf_duration_seconds(payload, "neg"), 0.0)
        self.assertEqual(cli._read_conf_duration_seconds(payload, "bad"), 0.0)

    @patch("tickertrail.cli._progress_stop")
    @patch("tickertrail.cli._progress_start")
    @patch(
        "tickertrail.cli._batch_index_snapshots",
        return_value={"A.NS": {"regularMarketPrice": 10.0}, "B.NS": {"regularMarketPrice": 11.0}},
    )
    def test_fetch_group_snapshots_wraps_progress_scope(self, _mock_batch, mock_start, mock_stop):
        snaps, passes = cli._fetch_group_snapshots_with_retries(["A.NS", "B.NS"])
        self.assertEqual(passes, 1)
        self.assertEqual(snaps["A.NS"]["regularMarketPrice"], 10.0)
        self.assertEqual(snaps["B.NS"]["regularMarketPrice"], 11.0)
        mock_start.assert_called_once_with("Resolving snap rows")
        mock_stop.assert_called_once()

    @patch("tickertrail.cli._progress_stop")
    @patch("tickertrail.cli._progress_start")
    @patch("tickertrail.cli._batch_index_snapshots", return_value={"^NSEI": {"regularMarketPrice": 10.0}})
    def test_resolve_group_candidate_snapshots_wraps_progress_scope(self, _mock_batch, mock_start, mock_stop):
        out, passes = cli._resolve_group_candidate_snapshots({"^NSEI": ["^NSEI"]})
        self.assertEqual(passes, 1)
        self.assertIn("^NSEI", out)
        mock_start.assert_called_once_with("Resolving index board")
        mock_stop.assert_called_once()

    def test_sign_and_range_extra_edges(self):
        self.assertEqual(cli._color_by_sign(-1.0, plus_is_green=False), "green")
        self.assertEqual(cli._range_line(10.0, 10.0, 10.0), "[n/a]")

    def test_enable_repl_history_import_fail(self):
        with patch("builtins.__import__", side_effect=ImportError):
            cli._enable_repl_history()

    def test_enable_repl_history_read_error_path(self):
        fake_readline = MagicMock()
        fake_readline.parse_and_bind.side_effect = RuntimeError("bind error")
        with patch.dict("sys.modules", {"readline": fake_readline}), patch.object(
            cli, "_HISTORY_FILE", cli.Path("/tmp/history_exists")
        ):
            with patch.object(cli.Path, "exists", return_value=True):
                cli._enable_repl_history()
        self.assertTrue(fake_readline.read_history_file.called)

    def test_enable_repl_history_success_path(self):
        fake_readline = MagicMock()
        with patch.dict("sys.modules", {"readline": fake_readline}), patch("atexit.register") as reg:
            with patch.object(cli, "_HISTORY_FILE", cli.Path("/tmp/nonexistent_history_file_for_test")):
                cli._enable_repl_history()
            self.assertTrue(fake_readline.set_history_length.called)
            self.assertTrue(fake_readline.parse_and_bind.called)
            self.assertTrue(reg.called)
            # exercise registered save callback branch
            cb = reg.call_args[0][0]
            fake_readline.write_history_file.side_effect = RuntimeError("x")
            cb()

    def test_formatter_extra_branches(self):
        class X:
            def __float__(self):
                raise ValueError("bad")

        self.assertEqual(cli._fmt_price(X()), "n/a")
        self.assertTrue(cli._fmt_compact_num(2_000_000_000).endswith("B"))
        self.assertTrue(cli._fmt_compact_num(2_000_000_000_000).endswith("T"))
        self.assertEqual(cli._fmt_compact_num(12), "12")

    def test_candidate_symbol_extra_branches(self):
        self.assertEqual(cli._candidate_symbols("   "), [])
        self.assertEqual(cli._candidate_symbols("NIFTY"), ["^NSEI"])
        self.assertEqual(cli._candidate_symbols("abc.ns"), ["ABC.NS"])
        self.assertEqual(cli._candidate_symbols("^IXIC"), ["^IXIC"])
        self.assertEqual(cli._candidate_symbols("nasdaq"), ["^IXIC"])
        self.assertEqual(cli._candidate_symbols("nasadq"), ["^IXIC"])
        self.assertEqual(cli._candidate_symbols("dow"), ["^DJI"])
        self.assertEqual(cli._candidate_symbols("hangseng"), ["^HSI"])
        self.assertEqual(cli._candidate_symbols("ftse"), ["^FTSE"])
        self.assertEqual(cli._candidate_symbols("ftse100"), ["^FTSE"])
        self.assertEqual(cli._candidate_symbols("nsebank"), ["^NSEBANK"])
        self.assertEqual(cli._candidate_symbols("banknifty"), ["^NSEBANK"])
        self.assertEqual(cli._candidate_symbols("smallcap"), ["^NSESMCP100"])
        self.assertEqual(cli._candidate_symbols("midcap"), ["^CNXMIDCAP"])
        self.assertEqual(cli._candidate_symbols("midcap select"), ["^NSEMDCP50"])
        self.assertEqual(cli._candidate_symbols("select"), ["^NSEMDCP50"])
        self.assertEqual(cli._candidate_symbols("vix"), ["^INDIAVIX"])
        self.assertEqual(cli._candidate_symbols("finnifty"), ["NIFTY_FIN_SERVICE.NS"])
        self.assertEqual(cli._candidate_symbols("psubank"), ["^CNXPSUBANK"])
        self.assertEqual(cli._candidate_symbols("bank"), ["^NSEBANK"])
        self.assertEqual(cli._candidate_symbols("infra"), ["^CNXINFRA"])
        self.assertEqual(cli._candidate_symbols("pharma"), ["^CNXPHARMA"])
        self.assertEqual(cli._candidate_symbols("fmcg"), ["^CNXFMCG"])
        self.assertEqual(cli._candidate_symbols("cpse"), ["^CNXPSE"])
        self.assertEqual(cli._candidate_symbols("niftyfmcg"), ["^CNXFMCG"])
        self.assertEqual(cli._candidate_symbols("niftydefence"), ["^CNXDEFENCE"])
        self.assertEqual(cli._candidate_symbols("niftypse"), ["^CNXPSE"])
        self.assertEqual(cli._candidate_symbols("niftyauto"), ["^CNXAUTO"])
        self.assertEqual(cli._candidate_symbols("s&p"), ["^GSPC"])

    @patch("tickertrail.cli.yf.Ticker")
    def test_get_quote_payload_exception_branches(self, mock_ticker):
        t = MagicMock()
        type(t).fast_info = property(lambda _s: (_ for _ in ()).throw(RuntimeError("x")))
        type(t).info = property(lambda _s: (_ for _ in ()).throw(RuntimeError("y")))
        mock_ticker.return_value = t
        out = cli._get_quote_payload("X")
        self.assertEqual(out, {})

    @patch("tickertrail.cli._get_quote_payload", return_value={})
    def test_resolve_symbol_all_fail(self, _mock_payload):
        sym, info = cli._resolve_symbol("abc")
        self.assertEqual(sym, "ABC.NS")
        self.assertIsNone(info)

    def test_resolve_symbol_empty_input_returns_none_info(self):
        sym, info = cli._resolve_symbol("   ")
        self.assertEqual(sym, "   ")
        self.assertIsNone(info)

    @patch("sys.stdin.isatty", return_value=True)
    def test_choose_symbol_cancel(self, _mock_tty):
        with patch("builtins.input", side_effect=["0"]):
            out = cli._choose_symbol_from_options("x", [{"symbol": "A", "name": "A", "exchange": "NSE", "type": "EQUITY"}])
        self.assertEqual(out, "A")
        with patch("builtins.input", side_effect=["0"]):
            out2 = cli._choose_symbol_from_options(
                "x",
                [
                    {"symbol": "A", "name": "A", "exchange": "NSE", "type": "EQUITY"},
                    {"symbol": "B", "name": "B", "exchange": "NSE", "type": "EQUITY"},
                ],
            )
        self.assertIsNone(out2)

    @patch("sys.stdin.isatty", return_value=False)
    def test_choose_symbol_non_tty_multiple_options_returns_none(self, _mock_tty):
        with patch("sys.stderr", new_callable=io.StringIO) as err:
            out = cli._choose_symbol_from_options(
                "bank",
                [
                    {"symbol": "SBIN.NS", "name": "STATE BANK", "exchange": "NSE", "type": "EQUITY"},
                    {"symbol": "BANKBARODA.NS", "name": "BANK OF BARODA", "exchange": "NSE", "type": "EQUITY"},
                ],
            )
        self.assertIsNone(out)
        self.assertIn("Top matches", err.getvalue())

    def test_search_symbol_options_blank_query(self):
        self.assertEqual(cli._search_symbol_options("   "), [])

    def test_load_nse_universe_missing_file_and_skip_invalid_rows(self):
        old_csv = cli._NSE_UNIVERSE_CSV
        old_cache = cli._NSE_UNIVERSE_CACHE
        try:
            cli._NSE_UNIVERSE_CACHE = None
            cli._NSE_UNIVERSE_CSV = cli.Path("/tmp/does_not_exist_scan_test.csv")
            self.assertEqual(cli._load_nse_universe(), [])
            with tempfile.TemporaryDirectory() as td:
                csv_path = cli.Path(td) / "nse.csv"
                csv_path.write_text(
                    "SYMBOL,NAME OF COMPANY\nGOOD,GOOD LTD\nBAD,\n,EMPTY\n",
                    encoding="utf-8",
                )
                cli._NSE_UNIVERSE_CACHE = None
                cli._NSE_UNIVERSE_CSV = csv_path
                rows = cli._load_nse_universe()
                self.assertEqual(rows, [{"symbol": "GOOD", "name": "GOOD LTD"}])
        finally:
            cli._NSE_UNIVERSE_CSV = old_csv
            cli._NSE_UNIVERSE_CACHE = old_cache

    def test_load_nse_universe_oserror_guard(self):
        old_cache = cli._NSE_UNIVERSE_CACHE
        old_csv = cli._NSE_UNIVERSE_CSV
        try:
            cli._NSE_UNIVERSE_CACHE = None
            cli._NSE_UNIVERSE_CSV = cli.Path("/tmp/nse_open_oserror.csv")
            with patch.object(cli.Path, "exists", return_value=True), patch.object(
                cli.Path, "open", side_effect=OSError("too many open files")
            ):
                self.assertEqual(cli._load_nse_universe(), [])
        finally:
            cli._NSE_UNIVERSE_CACHE = old_cache
            cli._NSE_UNIVERSE_CSV = old_csv

    def test_period_days_units(self):
        self.assertEqual(cli._period_token_days("7d"), 7)
        self.assertEqual(cli._period_token_days("2w"), 14)
        self.assertEqual(cli._period_token_days("3mo"), 90)
        self.assertEqual(cli._period_token_days("4y"), 1460)
        self.assertIsNone(cli._period_token_days("max"))

    def test_validate_interval_more_branches(self):
        self.assertIsNotNone(cli._validate_period_interval("max", "1m"))
        self.assertIsNotNone(cli._validate_period_interval("1y", "bad"))
        self.assertIsNone(cli._validate_period_interval("1y", "1wk"))

    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("X", None))
    def test_resolve_benchmark_helpers_error(self, _mock_resolve):
        s, l, e = cli._resolve_benchmark_for_table("AAPL", None, "bad")
        self.assertIsNone(s)
        self.assertIsNotNone(e)
        s2, e2 = cli._resolve_benchmark_override("bad")
        self.assertIsNone(s2)
        self.assertIsNotNone(e2)

    def test_benchmark_market_helpers(self):
        self.assertEqual(cli._benchmark_symbol_for("RELIANCE.NS", {"currency": "INR"})[0], "^NSEI")
        self.assertEqual(cli._benchmark_symbol_for("^NSEI", {"currency": "INR"}), (None, None))
        self.assertEqual(cli._benchmark_symbol_for("AAPL", {"currency": "USD"})[0], "^IXIC")
        self.assertEqual(cli._benchmark_symbol_for("^IXIC", {"currency": "USD"}), (None, None))
        self.assertEqual(cli._market_profile_for("AAPL", {"currency": "USD"})[1:], (9, 30, 16, 0))

    def test_extend_intraday_edges_and_downsample(self):
        p, pr = cli._extend_intraday_to_close([], [], "5m", "AAPL", {"currency": "USD"})
        self.assertEqual((p, pr), ([], []))
        p2, pr2 = cli._extend_intraday_to_close(
            [dt.datetime(2026, 2, 16, 21, 0, tzinfo=dt.timezone.utc)],
            [1.0],
            "x",
            "AAPL",
            {"currency": "USD"},
        )
        self.assertEqual((p2, pr2), ([dt.datetime(2026, 2, 16, 21, 0, tzinfo=dt.timezone.utc)], [1.0]))
        d, v = cli._downsample_series(["a", "b", "c", "d"], [1, 2, 3, 4], 3)
        self.assertEqual(d[-1], "d")
        self.assertEqual(v[-1], 4)

    def test_build_rebased_frame_none_conditions(self):
        tz = dt.timezone.utc
        self.assertIsNone(cli._build_rebased_frame([], [], [], [], tz, False))
        s_pts = [dt.datetime(2026, 1, 1, tzinfo=tz)]
        b_pts = [dt.datetime(2026, 1, 1, tzinfo=tz)]
        self.assertIsNone(cli._build_rebased_frame(s_pts, [0.0], b_pts, [1.0], tz, False))

    @patch("tickertrail.cli._get_quote_payload", return_value={})
    @patch("tickertrail.cli._fetch_daily_ohlcv_for_period", return_value=([], [], [], [], []))
    def test_print_quote_no_info(self, _mock_daily, _mock_q):
        with patch("sys.stderr", new_callable=io.StringIO):
            rc = cli._print_quote("X", "X", include_after_hours=True)
        self.assertEqual(rc, 2)

    @patch("tickertrail.cli._fetch_daily_ohlcv_for_period")
    def test_print_quote_full(self, mock_daily):
        points = [dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(days=i) for i in range(40)]
        closes = [100.0 + float(i) for i in range(40)]
        volumes = [1_000_000.0 + float(i * 1_000) for i in range(40)]
        mock_daily.return_value = (points, closes, [None] * 40, [None] * 40, volumes)
        info = {
            "shortName": "INFY",
            "currency": "INR",
            "regularMarketPrice": 100.0,
            "regularMarketPreviousClose": 99.0,
            "regularMarketOpen": 99.5,
            "regularMarketDayLow": 98.0,
            "regularMarketDayHigh": 101.0,
            "regularMarketVolume": 1000,
            "marketCap": 10_000_000,
            "fiftyTwoWeekLow": 80.0,
            "fiftyTwoWeekHigh": 120.0,
            "trailingPE": 20.0,
            "trailingPegRatio": 1.2,
            "returnOnEquity": 0.2,
            "returnOnCapitalEmployed": 0.25,
            "freeCashflow": 100_000_000,
            "postMarketPrice": 100.1,
        }
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_quote("INFY", "INFY.NS", include_after_hours=True, preloaded_info=info)
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("PE(TTM)", txt)
        self.assertIn("Day Range", txt)
        self.assertGreater(txt.find("30D Moves"), txt.find("52W Range"))
        self.assertGreater(txt.find("Returns"), txt.find("30D Moves"))
        self.assertGreater(txt.find("Signal"), txt.find("Returns"))
        self.assertIn("7D", txt)
        self.assertIn("1MO", txt)
        self.assertIn("3MO", txt)
        self.assertIn("6MO", txt)
        self.assertIn("9MO", txt)
        self.assertIn("Signal", txt)
        self.assertIn("Risk", txt)
        self.assertIn("Extremes", txt)
        mock_daily.assert_called_once_with("INFY.NS", "1y")

    @patch("tickertrail.cli._fetch_daily_ohlcv_for_period", return_value=([], [], [], [], []))
    def test_print_quote_year_low_high_fallback_and_no_afterhours(self, _mock_daily):
        info = {
            "longName": "TEST LTD",
            "currency": "INR",
            "regularMarketPrice": 100.0,
            "regularMarketPreviousClose": 99.0,
            "regularMarketOpen": 99.5,
            "regularMarketDayLow": 98.0,
            "regularMarketDayHigh": 101.0,
            "regularMarketVolume": None,
            "marketCap": None,
            "yearLow": 80.0,
            "yearHigh": 120.0,
        }
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_quote("T", "T.NS", include_after_hours=False, preloaded_info=info)
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("TEST LTD", txt)
        self.assertIn("52W Range", txt)
        self.assertIn("Returns", txt)
        self.assertIn("Signal", txt)

    @patch("tickertrail.cli._fetch_daily_ohlcv_for_period", return_value=([], [], [], [], []))
    def test_print_quote_afterhours_pre_only(self, _mock_daily):
        info = {
            "shortName": "X",
            "currency": "USD",
            "regularMarketPrice": 10.0,
            "regularMarketPreviousClose": 9.0,
            "regularMarketOpen": 9.5,
            "regularMarketDayLow": 9.0,
            "regularMarketDayHigh": 10.0,
            "preMarketPrice": 9.9,
        }
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_quote("X", "X", include_after_hours=True, preloaded_info=info)
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Ext Pre", txt)
        self.assertIn("Returns", txt)
        self.assertIn("Risk", txt)

    @patch("tickertrail.cli._fetch_daily_ohlcv_for_period", return_value=([], [], [], [], []))
    def test_print_quote_ratio_and_float_guard_branches(self, _mock_daily):
        info = {
            "shortName": "X",
            "currency": "USD",
            "regularMarketPrice": 10.0,
            "regularMarketPreviousClose": 9.0,
            "regularMarketOpen": 9.5,
            "regularMarketDayLow": "bad",
            "regularMarketDayHigh": "bad",
            "fiftyTwoWeekLow": "bad",
            "fiftyTwoWeekHigh": "bad",
            "forwardPE": 15.0,
            "trailingPegRatio": "bad",
            "returnOnEquity": "bad",
        }
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_quote("X", "X", include_after_hours=False, preloaded_info=info)
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("PE(FWD)", txt)
        self.assertIn("PEG n/a", txt)
        self.assertIn("ROE n/a", txt)

    @patch("tickertrail.cli.yf.download")
    def test_fetch_day_range_fallback_empty_and_exception(self, mock_dl):
        mock_dl.return_value = pd.DataFrame()
        self.assertEqual(cli._fetch_day_range_fallback("X"), (None, None))
        mock_dl.side_effect = RuntimeError("x")
        self.assertEqual(cli._fetch_day_range_fallback("X"), (None, None))

    @patch("tickertrail.cli.yf.download", return_value=pd.DataFrame())
    def test_fetch_close_points_invalid_custom_token(self, _mock_dl):
        pts, prices = cli._fetch_close_points_for_token("X", "3m", "1d")
        self.assertEqual((pts, prices), ([], []))

    @patch("tickertrail.cli.yf.download")
    def test_fetch_close_points_custom_range_and_multiindex_close(self, mock_dl):
        idx = pd.date_range("2026-02-16", periods=2, freq="D", tz="UTC")
        cols = pd.MultiIndex.from_product([["Close"], ["X"]])
        df = pd.DataFrame([[10.0], [11.0]], index=idx, columns=cols)
        mock_dl.return_value = df
        pts, prices = cli._fetch_close_points_for_token("X", "7d", "1d")
        self.assertEqual(len(pts), 2)
        self.assertEqual(prices, [10.0, 11.0])

    @patch("tickertrail.cli.price_history._cache_get", return_value=None)
    @patch("tickertrail.cli.yf.download")
    def test_fetch_close_points_custom_range_empty_result(self, mock_dl, _mock_cache_get):
        mock_dl.return_value = pd.DataFrame()
        self.assertEqual(cli._fetch_close_points_for_token("X", "7d", "1d"), ([], []))

    @patch("tickertrail.cli.yf.download")
    def test_fetch_day_range_fallback_multiindex_and_invalid_range(self, mock_dl):
        idx = pd.date_range("2026-02-16 09:15", periods=2, freq="5min", tz="UTC")
        cols = pd.MultiIndex.from_product([["Low", "High"], ["X"]])
        df = pd.DataFrame([[10.0, 10.0], [10.0, 10.0]], index=idx, columns=cols)
        mock_dl.return_value = df
        self.assertEqual(cli._fetch_day_range_fallback("X"), (None, None))

    def test_series_for_symbol_field_branch_paths(self):
        idx = pd.date_range("2026-02-16", periods=2, tz="UTC")
        df_ticker_field = pd.DataFrame(
            [[10.0, 8.0], [11.0, 9.0]],
            index=idx,
            columns=pd.MultiIndex.from_product([["X"], ["Close", "Low"]]),
        )
        self.assertIsNotNone(cli._series_for_symbol_field(df_ticker_field, "X", "Close"))
        self.assertIsNone(cli._series_for_symbol_field(df_ticker_field, "Y", "High"))
        simple_df = pd.DataFrame({"Close": [1.0, 2.0]}, index=idx)
        self.assertIsNone(cli._series_for_symbol_field(simple_df, "X", "High"))
        nan_df = pd.DataFrame({"Close": [None, None]}, index=idx)
        self.assertIsNone(cli._series_for_symbol_field(nan_df, "X", "Close"))

    @patch("tickertrail.cli._colorize", side_effect=lambda txt, color: color[0].upper())
    @patch("tickertrail.cli._fetch_close_points_for_token")
    def test_recent_direction_dots_colors_up_down_flat(self, mock_fetch, _mock_color):
        mock_fetch.return_value = ([], [10, 11, 10, 10, 9, 10, 11, 11, 10, 11, 12])
        dots = cli._recent_direction_dots("X", days=10)
        self.assertEqual(dots, "GRYRGGYRGG")
        self.assertEqual(mock_fetch.call_args.args[1], "33d")

    @patch("tickertrail.cli._fetch_close_points_for_token", return_value=([], [10, 11, 12]))
    def test_recent_direction_dots_returns_none_for_insufficient_points(self, _mock_fetch):
        self.assertIsNone(cli._recent_direction_dots("X", days=10))

    def test_count_green_days_from_closes(self):
        self.assertEqual(cli._count_green_days_from_closes([1.0, 2.0, 1.0, 3.0], days=3), 2)
        self.assertIsNone(cli._count_green_days_from_closes([1.0, 2.0], days=3))
        self.assertEqual(cli._parse_moves_period([]), ("1mo", None))
        self.assertEqual(cli._parse_moves_period(["6mo"]), ("6mo", None))
        self.assertIsNone(cli._parse_moves_period(["2y"])[0])
        self.assertEqual(cli._parse_moves_period(["1mo", "1y"])[0], None)
        self.assertAlmostEqual(cli._period_return_from_closes([100.0, 110.0]) or 0.0, 10.0, places=8)
        self.assertIsNone(cli._period_return_from_closes([100.0]))
        self.assertIsNone(cli._period_return_from_closes([0.0, 10.0]))
        self.assertEqual(cli._parse_corr_period([]), ("1mo", None))
        self.assertEqual(cli._parse_corr_period(["3mo"]), ("3mo", None))
        self.assertEqual(cli._parse_corr_period(["7d"])[0], None)
        self.assertEqual(cli._parse_corr_period(["1mo", "3mo"])[0], None)
        self.assertEqual(cli._moves_days_for_period("custom"), 30)

    @patch("tickertrail.cli._fetch_close_points_for_token", return_value=([dt.datetime(2026, 1, 1)], [100.0]))
    def test_close_series_for_period_wrapper(self, mock_fetch):
        points, closes = cli._close_series_for_period("A.NS", "1mo")
        self.assertEqual(points, [dt.datetime(2026, 1, 1)])
        self.assertEqual(closes, [100.0])
        self.assertEqual(mock_fetch.call_args.kwargs["period_token"], "1mo")
        self.assertEqual(mock_fetch.call_args.kwargs["interval"], "1d")

    @patch("tickertrail.cli._close_series_for_period")
    def test_daily_return_series_for_period_success(self, mock_close):
        tz = dt.timezone.utc
        points = [dt.datetime(2026, 1, 1, tzinfo=tz), dt.datetime(2026, 1, 2, tzinfo=tz), dt.datetime(2026, 1, 3, tzinfo=tz)]
        mock_close.return_value = (points, [100.0, 110.0, 121.0])
        series = cli._daily_return_series_for_period("A.NS", "1mo")
        self.assertIsNotNone(series)
        assert series is not None
        self.assertEqual(len(series), 2)

    def test_moves_targets_for_context_extra_paths(self):
        with patch("tickertrail.cli._watchlist_symbols", return_value=[]), patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(cli._moves_targets_for_context(current_symbol=None, active_watchlist="swing"), (None, None))
        with patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(cli._moves_targets_for_context(current_symbol=None, active_watchlist=None), (None, None))
        with patch("tickertrail.cli._is_known_index_symbol", return_value=True), patch(
            "tickertrail.cli._snap_universe_for_symbol", return_value=("IDX", ("A.NS", "B.NS", "A.NS"))
        ):
            self.assertEqual(
                cli._moves_targets_for_context(current_symbol="^NSEI", active_watchlist=None),
                ("IDX", ["A.NS", "B.NS"]),
            )
        with patch("tickertrail.cli._is_known_index_symbol", return_value=False):
            self.assertEqual(
                cli._moves_targets_for_context(current_symbol="infy.ns", active_watchlist=None),
                ("INFY.NS", ["infy.ns"]),
            )

    def test_parse_scope_override_helpers(self):
        self.assertEqual(
            cli._parse_scope_override_with_period([], command_name="moves", period_tokens=cli._MOVES_PERIODS, default_period="1mo"),
            (None, "1mo", None),
        )
        self.assertEqual(
            cli._parse_scope_override_with_period(
                ["3mo"],
                command_name="moves",
                period_tokens=cli._MOVES_PERIODS,
                default_period="1mo",
            ),
            (None, "3mo", None),
        )
        scoped_symbols, scoped_period, scoped_err = cli._parse_scope_override_with_period(
            ["on", "infy", "tcs", "6mo"],
            command_name="moves",
            period_tokens=cli._MOVES_PERIODS,
            default_period="1mo",
        )
        self.assertEqual((scoped_symbols, scoped_period, scoped_err), (["infy", "tcs"], "6mo", None))
        self.assertIn(
            "Usage: moves",
            cli._parse_scope_override_with_period(
                ["on", "infy", "2y"],
                command_name="moves",
                period_tokens=cli._MOVES_PERIODS,
                default_period="1mo",
            )[2]
            or "",
        )
        self.assertEqual(cli._parse_scope_override_no_period([], command_name="trend"), (None, None))
        self.assertEqual(
            cli._parse_scope_override_no_period(["on", "infy", "tcs"], command_name="trend"),
            (["infy", "tcs"], None),
        )
        self.assertIn(
            "Usage: trend",
            cli._parse_scope_override_no_period(["infy"], command_name="trend")[1] or "",
        )

    def test_parse_relret_args_with_vs_and_on(self):
        self.assertEqual(cli._parse_relret_args([]), (None, "1mo", None, None))
        self.assertEqual(cli._parse_relret_args(["3mo"]), (None, "3mo", None, None))
        self.assertEqual(cli._parse_relret_args(["3mo", "vs", "it"]), (None, "3mo", "it", None))
        self.assertEqual(cli._parse_relret_args(["vs", "it", "6mo"]), (None, "6mo", "it", None))
        self.assertEqual(
            cli._parse_relret_args(["on", "infy", "tcs", "6mo", "vs", "it"]),
            (["infy", "tcs"], "6mo", "it", None),
        )
        self.assertEqual(
            cli._parse_relret_args(["on", "infy", "tcs", "vs", "it", "6mo"]),
            (["infy", "tcs"], "6mo", "it", None),
        )
        self.assertEqual(cli._parse_relret_args(["vs", "it"]), (None, "1mo", "it", None))
        self.assertIn("Usage: relret", cli._parse_relret_args(["on", "vs", "it"])[3] or "")
        self.assertIn("Usage: relret", cli._parse_relret_args(["on", "infy", "vs"])[3] or "")
        self.assertIn("Usage: relret", cli._parse_relret_args(["on", "infy", "6mo", "vs", "it", "3mo"])[3] or "")

    @patch("tickertrail.cli._resolve_symbol_with_fallback")
    def test_resolve_analytics_symbol_inputs_success_and_failure(self, mock_resolve):
        mock_resolve.side_effect = [
            ("INFY.NS", {"regularMarketPrice": 1.0}),
            ("TCS.NS", {"regularMarketPrice": 1.0}),
            ("INFY.NS", {"regularMarketPrice": 1.0}),
            ("BAD", None),
        ]
        self.assertEqual(cli._resolve_analytics_symbol_inputs(["infy", "tcs", "infy"]), ["INFY.NS", "TCS.NS"])
        with patch("sys.stderr", new_callable=io.StringIO) as err:
            self.assertIsNone(cli._resolve_analytics_symbol_inputs(["bad"]))
            self.assertIn("Could not resolve symbol", err.getvalue())

    @patch("tickertrail.cli._colorize", side_effect=lambda txt, color: color[0].upper())
    @patch("tickertrail.cli._fetch_close_points_for_token")
    def test_recent_direction_dots_ignores_nan_values(self, mock_fetch, _mock_color):
        mock_fetch.return_value = ([], [10, 11, float("nan"), 12, 13, 14, 15, 16, 17, 18, 19, 20])
        dots = cli._recent_direction_dots("X", days=10)
        self.assertEqual(dots, "GGGGGGGGGG")

    @patch("tickertrail.cli._fetch_close_points_for_token")
    def test_print_moves_snapshot_sorts_by_green_days_desc(self, mock_fetch):
        def side_effect(symbol, _period, _interval):
            data = {
                "A.NS": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],  # 7 green
                "B.NS": [1.0, 2.0, 1.0, 2.0, 3.0, 2.0, 3.0, 4.0],  # 5 green
                "C.NS": [8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0],  # 0 green
            }
            return ([], data[symbol])

        mock_fetch.side_effect = side_effect
        with (
            patch("tickertrail.cli._watchlist_symbols", return_value=None),
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            rc = cli._print_moves_snapshot(current_symbol=None, active_watchlist="swing", period_token="7d")
        self.assertEqual(rc, 3)

        with (
            patch("tickertrail.cli._watchlist_symbols", return_value=["B.NS", "C.NS", "A.NS"]),
            patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            rc = cli._print_moves_snapshot(current_symbol=None, active_watchlist="swing", period_token="7d")
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertLess(txt.index("A.NS"), txt.index("B.NS"))
        self.assertLess(txt.index("B.NS"), txt.index("C.NS"))

    @patch("tickertrail.cli._fetch_close_points_for_token", return_value=([], [1.0, 2.0, 3.0, 4.0]))
    def test_print_moves_snapshot_index_without_universe_falls_back_to_index_symbol(self, _mock_fetch):
        with (
            patch("tickertrail.cli._is_known_index_symbol", return_value=True),
            patch("tickertrail.cli._snap_universe_for_symbol", return_value=None),
            patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            rc = cli._print_moves_snapshot(current_symbol="^IXIC", active_watchlist=None, period_token="7d")
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("^IXIC", txt)

    @patch("tickertrail.cli._fetch_close_points_for_token", return_value=([], [1.0, 2.0, 3.0, 4.0]))
    @patch("tickertrail.cli._resolve_analytics_symbol_inputs", return_value=["INFY.NS", "TCS.NS"])
    def test_print_moves_snapshot_explicit_symbols_override_context(self, _mock_resolve, _mock_fetch):
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_moves_snapshot(current_symbol="^NSEI", active_watchlist="swing", period_token="1mo", explicit_symbols=["infy", "tcs"])
        self.assertEqual(rc, 0)
        self.assertIn("Explicit symbols", out.getvalue())

    @patch("tickertrail.cli._resolve_analytics_symbol_inputs", return_value=None)
    def test_print_moves_snapshot_explicit_symbols_resolution_failure(self, _mock_resolve):
        self.assertEqual(
            cli._print_moves_snapshot(current_symbol=None, active_watchlist=None, period_token="1mo", explicit_symbols=["bad"]),
            3,
        )

    @patch("tickertrail.cli._trend_score_for_symbol")
    def test_print_trend_snapshot_sorts_by_trend_score_desc(self, mock_trend_score):
        mock_trend_score.side_effect = [
            (3.0, 5.0),  # B.NS
            (1.0, 5.0),  # C.NS
            (5.0, 5.0),  # A.NS
        ]
        with (
            patch("tickertrail.cli._watchlist_symbols", return_value=["B.NS", "C.NS", "A.NS"]),
            patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            rc = cli._print_trend_snapshot(current_symbol=None, active_watchlist="swing")
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertLess(txt.index("A.NS"), txt.index("B.NS"))
        self.assertLess(txt.index("B.NS"), txt.index("C.NS"))

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_trend_snapshot", return_value=0)
    def test_run_repl_trend_command_and_usage(self, mock_trend, _mock_hist):
        with patch("builtins.input", side_effect=["trend", "trend 3mo", "exit"]):
            with patch("sys.stderr", new_callable=io.StringIO) as err:
                rc = cli._run_repl("BEL", "BEL.NS", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, 80, 20)
        self.assertEqual(rc, 0)
        self.assertEqual(mock_trend.call_count, 1)
        self.assertIn("Usage: trend", err.getvalue())

    @patch("tickertrail.cli._close_series_for_period")
    def test_print_relret_snapshot_sorts_by_outperformance(self, mock_series):
        tz = dt.timezone.utc
        points = [dt.datetime(2026, 1, 1, tzinfo=tz), dt.datetime(2026, 2, 1, tzinfo=tz)]

        def side_effect(symbol, _period=None, **_kwargs):
            mapping = {
                "^NSEI": (points, [100.0, 102.0]),  # +2.0%
                "A.NS": (points, [100.0, 105.0]),  # +5.0%
                "B.NS": (points, [100.0, 101.0]),  # +1.0%
                "C.NS": (points, [100.0]),  # n/a
            }
            return mapping[symbol]

        mock_series.side_effect = side_effect
        with (
            patch("tickertrail.cli._watchlist_symbols", return_value=["B.NS", "C.NS", "A.NS"]),
            patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            rc = cli._print_relret_snapshot(current_symbol=None, active_watchlist="swing", period_token="1mo")
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertLess(txt.index("A.NS"), txt.index("B.NS"))
        self.assertLess(txt.index("B.NS"), txt.index("C.NS"))
        lines = [line for line in txt.splitlines() if line.strip()]
        self.assertTrue(lines[-1].strip().startswith("WATCHLIST(EW)"))
        self.assertIn("+3.00%", lines[-1])
        self.assertIn("+1.00%", lines[-1])
        self.assertIn("\n\nWATCHLIST(EW)", txt)

    @patch("tickertrail.cli._daily_return_series_for_period")
    def test_print_corr_snapshot_outputs_summary(self, mock_series):
        idx = pd.Index([1, 2, 3], dtype="int64")
        mock_series.side_effect = [
            pd.Series([0.01, 0.02, 0.01], index=idx),
            pd.Series([0.01, 0.01, 0.02], index=idx),
            pd.Series([0.02, 0.01, 0.01], index=idx),
        ]
        with (
            patch("tickertrail.cli._watchlist_symbols", return_value=["A.NS", "B.NS", "C.NS"]),
            patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            rc = cli._print_corr_snapshot(current_symbol=None, active_watchlist="swing", period_token="1mo")
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Correlation Summary (1MO)", txt)
        self.assertIn("Most Positive Pairs", txt)
        self.assertIn("Most Negative Pairs", txt)
        self.assertIn("Near-Zero Pairs (Diversifiers)", txt)

    def test_print_corr_snapshot_needs_two_symbols(self):
        with (
            patch("tickertrail.cli._is_known_index_symbol", return_value=True),
            patch("tickertrail.cli._snap_universe_for_symbol", return_value=None),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = cli._print_corr_snapshot(current_symbol="^IXIC", active_watchlist=None, period_token="1mo")
        self.assertEqual(rc, 3)
        self.assertIn("at least two symbols", err.getvalue().lower())

    def test_relret_benchmark_for_context_paths(self):
        self.assertEqual(cli._relret_benchmark_for_context(None, "swing"), ("^NSEI", "NIFTY 50"))
        with patch("tickertrail.cli._is_known_index_symbol", return_value=True):
            self.assertEqual(cli._relret_benchmark_for_context("^CNXIT", None), ("^CNXIT", "NIFTY IT"))
            self.assertEqual(
                cli._relret_benchmark_for_context("NIFTY_NEXT_50.NS", None),
                ("^NIFTYNXT50", "NIFTY NEXT 50"),
            )
        with patch("tickertrail.cli._is_known_index_symbol", return_value=False):
            self.assertEqual(cli._relret_benchmark_for_context("^BSESN", None), ("^BSESN", "^BSESN"))
        with patch("tickertrail.cli._benchmark_symbol_for", return_value=("^IXIC", "NASDAQ")):
            self.assertEqual(cli._relret_benchmark_for_context("AAPL", None), ("^IXIC", "NASDAQ"))
        with patch("tickertrail.cli._benchmark_symbol_for", return_value=(None, None)):
            self.assertEqual(cli._relret_benchmark_for_context("AAPL", None), (None, "n/a"))

    @patch("tickertrail.cli._moves_targets_for_context", return_value=(None, None))
    def test_print_relret_snapshot_context_error(self, _mock_targets):
        self.assertEqual(cli._print_relret_snapshot(None, None, "1mo"), 3)

    @patch("tickertrail.cli._moves_targets_for_context", return_value=("X", ["A.NS"]))
    @patch("tickertrail.cli._relret_benchmark_for_context", return_value=(None, "n/a"))
    def test_print_relret_snapshot_no_benchmark(self, _mock_bench, _mock_targets):
        with patch("sys.stderr", new_callable=io.StringIO) as err:
            rc = cli._print_relret_snapshot(None, None, "1mo")
        self.assertEqual(rc, 3)
        self.assertIn("no benchmark available", err.getvalue().lower())

    @patch("tickertrail.cli._resolve_analytics_symbol_inputs", return_value=None)
    def test_print_relret_snapshot_explicit_symbols_resolution_failure(self, _mock_resolve):
        self.assertEqual(
            cli._print_relret_snapshot(current_symbol=None, active_watchlist=None, period_token="1mo", explicit_symbols=["bad"]),
            3,
        )

    @patch("tickertrail.cli._resolve_analytics_symbol_inputs", return_value=["A.NS", "B.NS"])
    @patch("tickertrail.cli._close_series_for_period")
    def test_print_relret_snapshot_explicit_symbols_uses_fixed_benchmark(self, mock_close, _mock_resolve):
        tz = dt.timezone.utc
        points = [dt.datetime(2026, 1, 1, tzinfo=tz), dt.datetime(2026, 2, 1, tzinfo=tz)]
        mock_close.side_effect = [
            (points, [100.0, 102.0]),  # ^NSEI benchmark
            (points, [100.0, 105.0]),  # A
            (points, [100.0, 101.0]),  # B
        ]
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_relret_snapshot(current_symbol="^NSEI", active_watchlist="swing", period_token="1mo", explicit_symbols=["a", "b"])
        self.assertEqual(rc, 0)
        txt = out.getvalue()
        self.assertIn("Explicit symbols", txt)
        self.assertNotIn("WATCHLIST(EW)", txt)

    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("^CNXIT", {"shortName": "NIFTY IT"}))
    @patch("tickertrail.cli._resolve_analytics_symbol_inputs", return_value=["A.NS", "B.NS"])
    @patch("tickertrail.cli._close_series_for_period")
    def test_print_relret_snapshot_explicit_symbols_with_benchmark_override(
        self,
        mock_close,
        _mock_resolve_symbols,
        _mock_resolve_benchmark,
    ):
        tz = dt.timezone.utc
        points = [dt.datetime(2026, 1, 1, tzinfo=tz), dt.datetime(2026, 2, 1, tzinfo=tz)]
        mock_close.side_effect = [
            (points, [100.0, 102.0]),  # benchmark from override
            (points, [100.0, 105.0]),  # A
            (points, [100.0, 101.0]),  # B
        ]
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_relret_snapshot(
                current_symbol=None,
                active_watchlist=None,
                period_token="1mo",
                explicit_symbols=["a", "b"],
                benchmark_input="it",
            )
        self.assertEqual(rc, 0)
        self.assertIn("NIFTY IT (^CNXIT)", out.getvalue())

    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("BAD", None))
    @patch("tickertrail.cli._resolve_analytics_symbol_inputs", return_value=["A.NS", "B.NS"])
    def test_print_relret_snapshot_benchmark_override_resolution_failure(self, _mock_resolve_symbols, _mock_resolve_benchmark):
        with patch("sys.stderr", new_callable=io.StringIO) as err:
            rc = cli._print_relret_snapshot(
                current_symbol=None,
                active_watchlist=None,
                period_token="1mo",
                explicit_symbols=["a", "b"],
                benchmark_input="bad",
            )
        self.assertEqual(rc, 3)
        self.assertIn("Could not resolve benchmark symbol", err.getvalue())

    @patch("tickertrail.cli._moves_targets_for_context", return_value=("Watchlist swing", ["A.NS"]))
    @patch("tickertrail.cli._relret_benchmark_for_context", return_value=("^NSEI", "NIFTY 50"))
    @patch("tickertrail.cli._close_series_for_period")
    def test_print_relret_snapshot_watchlist_no_valid_returns_summary_na(self, mock_close, _mock_bench, _mock_targets):
        tz = dt.timezone.utc
        points = [dt.datetime(2026, 1, 1, tzinfo=tz), dt.datetime(2026, 2, 1, tzinfo=tz)]
        mock_close.side_effect = [
            (points, [100.0, 101.0]),  # benchmark valid
            (points[:1], [100.0]),  # stock invalid return
        ]
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_relret_snapshot(current_symbol=None, active_watchlist="swing", period_token="1mo")
        self.assertEqual(rc, 0)
        self.assertIn("WATCHLIST(EW)", out.getvalue())
        self.assertIn("n/a", out.getvalue().lower())

    @patch("tickertrail.cli._moves_targets_for_context", return_value=("X", ["A.NS"]))
    @patch("tickertrail.cli._relret_benchmark_for_context", return_value=("^NSEI", "NIFTY 50"))
    @patch("tickertrail.cli._close_series_for_period")
    def test_print_relret_snapshot_no_benchmark_history(self, mock_close, _mock_bench, _mock_targets):
        mock_close.return_value = ([], [100.0])  # benchmark insufficient
        with patch("sys.stderr", new_callable=io.StringIO) as err:
            rc = cli._print_relret_snapshot(None, None, "1mo")
        self.assertEqual(rc, 3)
        self.assertIn("no historical data for benchmark", err.getvalue().lower())

    @patch("tickertrail.cli._moves_targets_for_context", return_value=("Index X", ["A.NS", "B.NS"]))
    @patch("tickertrail.cli._relret_benchmark_for_context", return_value=("^IXIC", "NASDAQ"))
    @patch("tickertrail.cli._close_series_for_period")
    def test_print_relret_snapshot_index_mode_skips_watchlist_summary(self, mock_close, _mock_bench, _mock_targets):
        tz = dt.timezone.utc
        points = [dt.datetime(2026, 1, 1, tzinfo=tz), dt.datetime(2026, 2, 1, tzinfo=tz)]
        mock_close.side_effect = [
            (points, [100.0, 102.0]),  # benchmark
            (points, [100.0, 105.0]),  # A
            (points, [100.0, 101.0]),  # B
        ]
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_relret_snapshot(current_symbol="^IXIC", active_watchlist=None, period_token="1mo")
        self.assertEqual(rc, 0)
        self.assertNotIn("WATCHLIST(EW)", out.getvalue())

    @patch("tickertrail.cli._close_series_for_period", return_value=([dt.datetime(2026, 1, 1)], [100.0]))
    def test_daily_return_series_for_period_short_series(self, _mock_close):
        self.assertIsNone(cli._daily_return_series_for_period("A.NS", "1mo"))

    @patch("tickertrail.cli._moves_targets_for_context", return_value=(None, None))
    def test_print_corr_snapshot_context_error(self, _mock_targets):
        self.assertEqual(cli._print_corr_snapshot(None, None, "1mo"), 3)

    @patch("tickertrail.cli._daily_return_series_for_period", return_value=None)
    @patch("tickertrail.cli._moves_targets_for_context", return_value=("X", ["A.NS", "B.NS"]))
    def test_print_corr_snapshot_not_enough_series(self, _mock_targets, _mock_series):
        with patch("sys.stderr", new_callable=io.StringIO) as err:
            rc = cli._print_corr_snapshot(None, None, "1mo")
        self.assertEqual(rc, 3)
        self.assertIn("not enough overlapping return series", err.getvalue().lower())

    @patch("tickertrail.cli._resolve_analytics_symbol_inputs", return_value=None)
    def test_print_corr_snapshot_explicit_symbols_resolution_failure(self, _mock_resolve):
        self.assertEqual(
            cli._print_corr_snapshot(current_symbol=None, active_watchlist=None, period_token="1mo", explicit_symbols=["bad"]),
            3,
        )

    @patch("tickertrail.cli._resolve_analytics_symbol_inputs", return_value=["A.NS"])
    def test_print_corr_snapshot_explicit_symbols_needs_two(self, _mock_resolve):
        with patch("sys.stderr", new_callable=io.StringIO) as err:
            rc = cli._print_corr_snapshot(current_symbol=None, active_watchlist=None, period_token="1mo", explicit_symbols=["a"])
        self.assertEqual(rc, 3)
        self.assertIn("at least two symbols", err.getvalue().lower())

    @patch("tickertrail.cli._moves_targets_for_context", return_value=("X", ["A.NS", "B.NS"]))
    @patch("tickertrail.cli._daily_return_series_for_period")
    def test_print_corr_snapshot_overlap_frame_too_small(self, mock_series, _mock_targets):
        idx_a = pd.Index([1, 2], dtype="int64")
        idx_b = pd.Index([2, 3], dtype="int64")
        mock_series.side_effect = [pd.Series([0.01, 0.02], index=idx_a), pd.Series([0.03, 0.04], index=idx_b)]
        with patch("sys.stderr", new_callable=io.StringIO) as err:
            rc = cli._print_corr_snapshot(current_symbol=None, active_watchlist=None, period_token="1mo")
        self.assertEqual(rc, 3)
        self.assertIn("not enough overlapping return series", err.getvalue().lower())

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_corr_snapshot", return_value=0)
    @patch("tickertrail.cli._print_relret_snapshot", return_value=0)
    def test_run_repl_relret_and_corr_commands(self, mock_relret, mock_corr, _mock_hist):
        with patch(
            "builtins.input",
            side_effect=[
                "relret",
                "rr",
                "relret 3mo",
                "relret on infy tcs 6mo",
                "relret on infy tcs 6mo vs it",
                "relret on infy tcs vs it 6mo",
                "corr",
                "corr 6mo",
                "corr on infy tcs 3mo",
                "exit",
            ],
        ):
            rc = cli._run_repl("BEL", "BEL.NS", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, 80, 20)
        self.assertEqual(rc, 0)
        self.assertEqual(mock_relret.call_count, 6)
        self.assertEqual(mock_relret.call_args_list[0].kwargs["period_token"], "1mo")
        self.assertEqual(mock_relret.call_args_list[1].kwargs["period_token"], "1mo")
        self.assertEqual(mock_relret.call_args_list[2].kwargs["period_token"], "3mo")
        self.assertEqual(mock_relret.call_args_list[3].kwargs["period_token"], "6mo")
        self.assertEqual(mock_relret.call_args_list[3].kwargs["explicit_symbols"], ["infy", "tcs"])
        self.assertEqual(mock_relret.call_args_list[4].kwargs["period_token"], "6mo")
        self.assertEqual(mock_relret.call_args_list[4].kwargs["benchmark_input"], "it")
        self.assertEqual(mock_relret.call_args_list[5].kwargs["period_token"], "6mo")
        self.assertEqual(mock_relret.call_args_list[5].kwargs["benchmark_input"], "it")
        self.assertEqual(mock_corr.call_count, 3)
        self.assertEqual(mock_corr.call_args_list[0].kwargs["period_token"], "1mo")
        self.assertEqual(mock_corr.call_args_list[1].kwargs["period_token"], "6mo")
        self.assertEqual(mock_corr.call_args_list[2].kwargs["period_token"], "3mo")
        self.assertEqual(mock_corr.call_args_list[2].kwargs["explicit_symbols"], ["infy", "tcs"])

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_trend_snapshot", return_value=0)
    @patch("tickertrail.cli._print_moves_snapshot", return_value=0)
    def test_run_repl_move_and_trends_aliases(self, mock_moves, mock_trend, _mock_hist):
        with patch(
            "builtins.input",
            side_effect=["move", "moves 3mo", "moves on infy tcs 7d", "trends", "trend on infy tcs", "exit"],
        ):
            rc = cli._run_repl("BEL", "BEL.NS", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, 80, 20)
        self.assertEqual(rc, 0)
        self.assertEqual(mock_moves.call_count, 3)
        self.assertEqual(mock_moves.call_args_list[0].kwargs["period_token"], "1mo")
        self.assertEqual(mock_moves.call_args_list[1].kwargs["period_token"], "3mo")
        self.assertEqual(mock_moves.call_args_list[2].kwargs["period_token"], "7d")
        self.assertEqual(mock_moves.call_args_list[2].kwargs["explicit_symbols"], ["infy", "tcs"])
        self.assertEqual(mock_trend.call_count, 2)
        self.assertEqual(mock_trend.call_args_list[1].kwargs["explicit_symbols"], ["infy", "tcs"])

    @patch("tickertrail.cli._fetch_close_points_for_token")
    def test_print_trend_snapshot_index_without_universe_falls_back_to_index_symbol(self, mock_fetch):
        tz = dt.timezone.utc
        points = [dt.datetime(2026, 1, 1, tzinfo=tz) + dt.timedelta(days=i) for i in range(230)]
        closes = [100.0 + float(i) for i in range(230)]
        mock_fetch.return_value = (points, closes)
        with (
            patch("tickertrail.cli._is_known_index_symbol", return_value=True),
            patch("tickertrail.cli._snap_universe_for_symbol", return_value=None),
            patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            rc = cli._print_trend_snapshot(current_symbol="^IXIC", active_watchlist=None)
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("^IXIC", txt)

    @patch("tickertrail.cli._fetch_close_points_for_token")
    def test_return_horizon_summary(self, mock_fetch):
        points = [dt.datetime(2025, 2, 17, tzinfo=dt.timezone.utc) + dt.timedelta(days=offset) for offset in (0, 92, 184, 275, 365)]
        closes = [100.0, 110.0, 120.0, 130.0, 140.0]
        mock_fetch.return_value = (points, closes)
        summary = cli._return_horizon_summary("X")
        self.assertAlmostEqual(summary["7D"] or 0.0, ((140.0 / 130.0) - 1.0) * 100.0, places=8)
        self.assertAlmostEqual(summary["1MO"] or 0.0, ((140.0 / 130.0) - 1.0) * 100.0, places=8)
        self.assertAlmostEqual(summary["3MO"] or 0.0, ((140.0 / 120.0) - 1.0) * 100.0, places=8)
        self.assertAlmostEqual(summary["6MO"] or 0.0, ((140.0 / 110.0) - 1.0) * 100.0, places=8)
        self.assertAlmostEqual(summary["9MO"] or 0.0, ((140.0 / 100.0) - 1.0) * 100.0, places=8)
        self.assertAlmostEqual(summary["1Y"] or 0.0, ((140.0 / 100.0) - 1.0) * 100.0, places=8)
        self.assertEqual(mock_fetch.call_args.args[1:], ("1y", "1d"))

    @patch("tickertrail.cli._fetch_close_points_for_token", return_value=([], [10.0]))
    def test_return_horizon_summary_insufficient_points(self, _mock_fetch):
        self.assertEqual(
            cli._return_horizon_summary("X"),
            {"7D": None, "1MO": None, "3MO": None, "6MO": None, "9MO": None, "1Y": None},
        )

    @patch("tickertrail.cli._fetch_daily_ohlcv_for_period")
    def test_signal_snapshot(self, mock_daily):
        points = [dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(days=i) for i in range(260)]
        closes = [100.0 + float(i * 0.2) for i in range(260)]
        volumes = [500_000.0 + float(i * 10.0) for i in range(260)]
        mock_daily.return_value = (points, closes, [None] * 260, [None] * 260, volumes)
        snapshot = cli._signal_snapshot("X")
        self.assertIsNotNone(snapshot.get("trend_score"))
        self.assertIsNotNone(snapshot.get("rsi14"))
        self.assertIsNotNone(snapshot.get("vol_vs_20d"))

    @patch(
        "tickertrail.cli._get_quote_payload",
        return_value={"regularMarketDayLow": 95.0, "regularMarketDayHigh": 105.0},
    )
    def test_enrich_snapshot_day_range_from_quote(self, _mock_quote):
        snap = {"regularMarketPrice": 100.0, "regularMarketDayLow": None, "regularMarketDayHigh": None}
        cli._enrich_snapshot_day_range_from_quote("A.NS", snap)
        self.assertEqual(snap["regularMarketDayLow"], 95.0)
        self.assertEqual(snap["regularMarketDayHigh"], 105.0)
        self.assertTrue(cli._has_usable_day_range(snap))

    @patch("tickertrail.cli._get_quote_payload")
    def test_enrich_snapshot_day_range_from_symbol_candidates_uses_fallback_symbol(self, mock_quote):
        def _fake_quote(symbol):
            if symbol == "NIFTY_NEXT_50.NS":
                return {"regularMarketPrice": 100.0}
            return {"regularMarketDayLow": 90.0, "regularMarketDayHigh": 110.0}

        mock_quote.side_effect = _fake_quote
        snap = {"regularMarketPrice": 100.0, "regularMarketDayLow": None, "regularMarketDayHigh": None}
        cli._enrich_snapshot_day_range_from_symbol_candidates(["NIFTY_NEXT_50.NS", "^NIFTYNXT50"], snap)
        self.assertEqual(snap["regularMarketDayLow"], 90.0)
        self.assertEqual(snap["regularMarketDayHigh"], 110.0)
        self.assertEqual(mock_quote.call_args_list[0].args[0], "NIFTY_NEXT_50.NS")
        self.assertEqual(mock_quote.call_args_list[1].args[0], "^NIFTYNXT50")

    def test_extract_quote_day_range_supports_daylow_alias_keys(self):
        info = {"dayLow": 101.5, "dayHigh": 109.25}
        self.assertEqual(cli._extract_quote_day_range(info), (101.5, 109.25))

    def test_extract_quote_day_range_supports_textual_day_range(self):
        info = {"regularMarketDayRange": "98.10 - 103.45"}
        self.assertEqual(cli._extract_quote_day_range(info), (98.10, 103.45))

    @patch("tickertrail.cli._get_quote_payload", return_value={"dayRange": "120 - 140"})
    def test_enrich_snapshot_day_range_from_quote_parses_day_range_text(self, _mock_quote):
        snap = {"regularMarketPrice": 130.0, "regularMarketDayLow": None, "regularMarketDayHigh": None}
        cli._enrich_snapshot_day_range_from_quote("^NIFTYNXT50", snap)
        self.assertEqual(snap["regularMarketDayLow"], 120.0)
        self.assertEqual(snap["regularMarketDayHigh"], 140.0)

    def test_batch_index_snapshots_empty_and_exception_paths(self):
        self.assertEqual(cli._batch_index_snapshots([]), {})
        with patch("tickertrail.cli.yf.download", side_effect=RuntimeError("x")):
            snaps = cli._batch_index_snapshots(["^NSEI"])
        self.assertIn("^NSEI", snaps)
        self.assertIsNone(snaps["^NSEI"]["regularMarketPrice"])

    @patch("tickertrail.cli._get_quote_payload", return_value={"regularMarketPrice": 10.0, "regularMarketPreviousClose": 9.0})
    @patch("tickertrail.cli._batch_index_snapshots")
    def test_fetch_group_snapshots_with_retries_policy(self, mock_batch, _mock_quote):
        def _fake_batch(symbols):
            if symbols == ["A.NS", "B.NS"]:
                return {"A.NS": {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, "B.NS": {"regularMarketPrice": None}}
            if symbols == ["B.NS"]:
                return {"B.NS": {"regularMarketPrice": None}}
            return {sym: {"regularMarketPrice": None} for sym in symbols}

        mock_batch.side_effect = _fake_batch
        snaps, passes = cli._fetch_group_snapshots_with_retries(["A.NS", "B.NS"])
        self.assertEqual(passes, 3)
        self.assertEqual(snaps["B.NS"]["regularMarketPrice"], 10.0)
        self.assertEqual(mock_batch.call_args_list[0].args[0], ["A.NS", "B.NS"])
        self.assertEqual(mock_batch.call_args_list[1].args[0], ["B.NS"])
        self.assertEqual(mock_batch.call_args_list[2].args[0], ["B.NS"])

    @patch(
        "tickertrail.cli._get_quote_payload",
        return_value={
            "regularMarketPrice": 1.0,
            "regularMarketPreviousClose": 1.0,
            "regularMarketDayLow": 0.9,
            "regularMarketDayHigh": 1.1,
        },
    )
    @patch("tickertrail.cli._batch_index_snapshots", return_value={"A.NS": {"regularMarketPrice": 1.0}})
    def test_fetch_group_snapshots_enriches_missing_day_range_from_quote(self, _mock_batch, _mock_quote):
        snaps, passes = cli._fetch_group_snapshots_with_retries(["A.NS"])
        self.assertEqual(passes, 1)
        self.assertEqual(snaps["A.NS"]["regularMarketDayLow"], 0.9)
        self.assertEqual(snaps["A.NS"]["regularMarketDayHigh"], 1.1)

    @patch("tickertrail.cli.snapshot_service.fetch_group_snapshots_with_retries", return_value=({}, 1))
    def test_fetch_group_snapshots_uses_silent_progress_for_single_symbol(self, mock_fetch):
        rc_snaps, rc_passes = cli._fetch_group_snapshots_with_retries(["A.NS"])
        self.assertEqual((rc_snaps, rc_passes), ({}, 1))
        progress_scope = mock_fetch.call_args.kwargs["progress_scope"]
        self.assertIs(progress_scope, cli._silent_progress_scope)

    @patch("tickertrail.cli._get_quote_payload", return_value={"regularMarketPrice": 2.0, "regularMarketPreviousClose": 1.0})
    @patch("tickertrail.cli._batch_index_snapshots")
    def test_fetch_group_snapshots_direct_ticker_fallback_after_three_batches(self, mock_batch, mock_quote):
        def _fake_batch(symbols):
            if symbols == ["A.NS", "B.NS"]:
                return {"A.NS": {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, "B.NS": {"regularMarketPrice": None}}
            if symbols == ["B.NS"]:
                return {"B.NS": {"regularMarketPrice": None}}
            return {sym: {"regularMarketPrice": None} for sym in symbols}

        mock_batch.side_effect = _fake_batch
        snaps, passes = cli._fetch_group_snapshots_with_retries(["A.NS", "B.NS"])
        self.assertEqual(passes, 3)
        self.assertEqual(snaps["B.NS"]["regularMarketPrice"], 2.0)
        self.assertTrue(mock_quote.called)

    @patch("tickertrail.cli.yf.download")
    def test_batch_index_snapshots_daily_fallbacks(self, mock_dl):
        idx_d = pd.date_range("2026-02-10", periods=2, freq="D", tz="UTC")
        daily_df = pd.DataFrame(
            {
                ("Close", "^NSEI"): [100.0, 101.0],
                ("Low", "^NSEI"): [98.0, 99.0],
                ("High", "^NSEI"): [102.0, 103.0],
            },
            index=idx_d,
        )
        mock_dl.return_value = daily_df
        snaps = cli._batch_index_snapshots(["^NSEI"])
        self.assertEqual(snaps["^NSEI"]["regularMarketPrice"], 101.0)
        self.assertEqual(snaps["^NSEI"]["regularMarketDayLow"], 99.0)
        self.assertEqual(snaps["^NSEI"]["regularMarketDayHigh"], 103.0)

    def test_period_agg_and_checkpoint_edge_helpers(self):
        self.assertIsNone(cli._normalize_period_token("0d"))
        self.assertIsNone(cli._period_token_days("bad"))
        self.assertEqual(cli._normalize_agg_token("1wk"), "1wk")
        self.assertEqual(cli._checkpoint_indices(0), [])
        self.assertEqual(len(cli._checkpoint_indices(10, points=6)), 6)
        parsed, err = cli._parse_compare_command_args(["a", "b", "w"])
        self.assertIsNone(parsed)
        self.assertIsNotNone(err)
        parsed2, err2 = cli._parse_compare_command_args(["a", "b", "bad", "w"])
        self.assertIsNone(parsed2)
        self.assertIn("Unsupported period token", str(err2))
        parsed3, err3 = cli._parse_compare_command_args(["a", "b", "1y", "w"])
        self.assertIsNotNone(parsed3)
        self.assertIsNone(err3)
        parsed4, err4 = cli._parse_compare_command_args(["a", "b", "bad"])
        self.assertIsNotNone(parsed4)
        self.assertIsNone(err4)

    def test_period_interval_default_helpers_extra_paths(self):
        self.assertEqual(cli._table_interval_for_period_token("max"), "1mo")
        self.assertEqual(cli._table_interval_for_period_token("bad"), "1d")
        self.assertEqual(cli._table_interval_for_period_token("1d"), "5m")
        self.assertEqual(cli._interval_for_chart_period("max"), "1mo")
        self.assertEqual(cli._interval_for_chart_period("bad"), "1d")
        self.assertEqual(cli._interval_for_chart_period("3y"), "1mo")

    def test_parse_swing_additional_success_and_error_paths(self):
        parsed_ok, err_ok = cli._parse_swing_command_args(["2y", "mo"], "c")
        self.assertIsNone(err_ok)
        self.assertIsNotNone(parsed_ok)
        parsed_bench, err_bench = cli._parse_swing_command_args(["nifty", "2y"], "c")
        self.assertIsNone(err_bench)
        self.assertIsNotNone(parsed_bench)
        parsed_bad_dash, err_bad_dash = cli._parse_swing_command_args(["nifty", "-", "2y", "qq"], "c")
        self.assertIsNone(parsed_bad_dash)
        self.assertIsNotNone(err_bad_dash)
        parsed_too_many, err_too_many = cli._parse_swing_command_args(["a", "b", "c", "d"], "c")
        self.assertIsNone(parsed_too_many)
        self.assertIsNotNone(err_too_many)

    def test_batch_index_snapshots_from_multiindex_frames(self):
        idx_d = pd.date_range("2026-02-10", periods=3, freq="D", tz="UTC")
        daily_cols = pd.MultiIndex.from_product(
            [["Close", "Low", "High"], ["^NSEI", "^IXIC"]]
        )
        daily_df = pd.DataFrame(
            [
                [100.0, 200.0, 99.0, 198.0, 101.0, 202.0],
                [101.0, 201.0, 100.0, 199.0, 102.0, 203.0],
                [102.0, 202.0, 101.0, 200.0, 103.0, 204.0],
            ],
            index=idx_d,
            columns=daily_cols,
        )
        with patch("tickertrail.cli.yf.download", return_value=daily_df):
            snaps = cli._batch_index_snapshots(["^NSEI", "^IXIC"])
        self.assertEqual(snaps["^NSEI"]["regularMarketPrice"], 102.0)
        self.assertEqual(snaps["^NSEI"]["regularMarketPreviousClose"], 101.0)
        self.assertEqual(snaps["^NSEI"]["regularMarketDayLow"], 101.0)
        self.assertEqual(snaps["^NSEI"]["regularMarketDayHigh"], 103.0)

    def test_parse_swing_len3_invalid(self):
        parsed, err = cli._parse_swing_command_args(["NIFTY", "3m", "w"], "t")
        self.assertIsNone(parsed)
        self.assertIsNotNone(err)

    def test_resolve_benchmark_none_and_override_none(self):
        s, l, e = cli._resolve_benchmark_for_table("AAPL", {"currency": "USD"}, None)
        self.assertEqual((s, l, e), ("^IXIC", "NASDAQ", None))
        s2, e2 = cli._resolve_benchmark_override(None)
        self.assertEqual((s2, e2), (None, None))

    def test_snap_symbol_normalization_and_universe_lookup(self):
        old_cache = cli._SNAP_UNIVERSE_CACHE
        old_csv = cli._INDEX_CONSTITUENTS_CSV
        try:
            with tempfile.TemporaryDirectory() as td:
                csv_path = cli.Path(td) / "index_constituents.csv"
                csv_path.write_text(
                    "index_symbol,index_label,constituent\n"
                    "^NSEI,NIFTY 50,AAA.NS\n"
                    "^CNXPSUBANK,NIFTY PSU BANK,BBB.NS\n",
                    encoding="utf-8",
                )
                cli._SNAP_UNIVERSE_CACHE = None
                cli._INDEX_CONSTITUENTS_CSV = csv_path
                self.assertEqual(cli._normalize_snap_index_symbol("^nsei"), "^NSEI")
                self.assertEqual(cli._normalize_snap_index_symbol("^cnxpsubank"), "^CNXPSUBANK")
                snap = cli._snap_universe_for_symbol("^NSEI")
                self.assertIsNotNone(snap)
                assert snap is not None
                self.assertEqual(snap[0], "NIFTY 50")
                self.assertIsNone(cli._snap_universe_for_symbol("^NSEMDCP50"))
        finally:
            cli._SNAP_UNIVERSE_CACHE = old_cache
            cli._INDEX_CONSTITUENTS_CSV = old_csv

    def test_snap_universe_covers_allowed_snap_indices(self):
        old = cli._SNAP_UNIVERSE_CACHE
        try:
            cli._SNAP_UNIVERSE_CACHE = None
            universes = cli._load_snap_universes()
            allowed = {s.upper() for s in cli._SNAP_ALLOWED_INDEX_SYMBOLS}
            board_symbols = [s.upper() for s, _ in cli._INDIA_INDEX_BOARD] + [s.upper() for s, _ in cli._GLOBAL_INDEX_BOARD]
            # Some supported indices can intentionally run snap in index-only mode
            # when constituent mappings are not configured in index_constituents.csv.
            allowed_without_universe = {"^NSEMDCP50"}
            missing = [s for s in board_symbols if s in allowed and s not in universes and s not in allowed_without_universe]
            self.assertEqual(missing, [])
            self.assertIsNone(cli._snap_universe_for_symbol("^INDIAVIX"))
            self.assertIsNone(cli._snap_universe_for_symbol("^IXIC"))
            self.assertIsNone(cli._snap_universe_for_symbol("^FTSE"))
            self.assertIsNone(cli._snap_universe_for_symbol("^FCHI"))
            self.assertIsNone(cli._snap_universe_for_symbol("^HSI"))
            self.assertIsNone(cli._snap_universe_for_symbol("^N225"))
        finally:
            cli._SNAP_UNIVERSE_CACHE = old

    def test_expected_constituent_count_helper(self):
        self.assertEqual(cli._expected_constituent_count("^NSEI"), 50)
        self.assertEqual(cli._expected_constituent_count("^CNXMIDCAP"), 100)
        self.assertIsNone(cli._expected_constituent_count("^CNXPHARMA"))

    def test_load_snap_universes_missing_and_invalid_rows(self):
        old_cache = cli._SNAP_UNIVERSE_CACHE
        old_csv = cli._INDEX_CONSTITUENTS_CSV
        try:
            cli._SNAP_UNIVERSE_CACHE = None
            cli._INDEX_CONSTITUENTS_CSV = cli.Path("/tmp/does_not_exist_snap_index.csv")
            self.assertEqual(cli._load_snap_universes(), {})
            with tempfile.TemporaryDirectory() as td:
                csv_path = cli.Path(td) / "index_constituents.csv"
                csv_path.write_text(
                    "index_symbol,index_label,constituent\n"
                    "^NSEI,NIFTY 50,AAA.NS\n"
                    "^NSEI,NIFTY 50,BBB.NS\n"
                    "^NSEI,,CCC.NS\n",
                    encoding="utf-8",
                )
                cli._SNAP_UNIVERSE_CACHE = None
                cli._INDEX_CONSTITUENTS_CSV = csv_path
                loaded = cli._load_snap_universes()
                self.assertIn("^NSEI", loaded)
                self.assertEqual(loaded["^NSEI"][1], ("AAA.NS", "BBB.NS"))
        finally:
            cli._SNAP_UNIVERSE_CACHE = old_cache
            cli._INDEX_CONSTITUENTS_CSV = old_csv

    def test_load_snap_universes_oserror_guard(self):
        old_cache = cli._SNAP_UNIVERSE_CACHE
        old_csv = cli._INDEX_CONSTITUENTS_CSV
        try:
            cli._SNAP_UNIVERSE_CACHE = None
            cli._INDEX_CONSTITUENTS_CSV = cli.Path("/tmp/snap_open_oserror.csv")
            with patch.object(cli.Path, "exists", return_value=True), patch.object(
                cli.Path, "open", side_effect=OSError("too many open files")
            ):
                self.assertEqual(cli._load_snap_universes(), {})
        finally:
            cli._SNAP_UNIVERSE_CACHE = old_cache
            cli._INDEX_CONSTITUENTS_CSV = old_csv

    @patch("tickertrail.cli._batch_index_snapshots")
    def test_print_index_constituent_snap_supported_and_unsupported(self, mock_snapshots):
        mock_snapshots.return_value = {
            "A.NS": {
                "regularMarketPrice": 100.0,
                "regularMarketPreviousClose": 95.0,
                "regularMarketDayLow": 90.0,
                "regularMarketDayHigh": 110.0,
            },
            "B.NS": {
                "regularMarketPrice": 95.0,
                "regularMarketPreviousClose": 100.0,
                "regularMarketDayLow": 90.0,
                "regularMarketDayHigh": 105.0,
            },
            "C.NS": {
                "regularMarketPrice": 98.0,
                "regularMarketPreviousClose": 100.0,
                "regularMarketDayLow": 95.0,
                "regularMarketDayHigh": 102.0,
            },
            "D.NS": {
                "regularMarketPrice": 110.0,
                "regularMarketPreviousClose": 100.0,
                "regularMarketDayLow": 95.0,
                "regularMarketDayHigh": 115.0,
            },
        }
        old = cli._SNAP_UNIVERSE_CACHE
        try:
            cli._SNAP_UNIVERSE_CACHE = {"^NSEI": ("TEST INDEX", ("A.NS", "B.NS", "C.NS", "D.NS"))}
            with patch("sys.stdout", new_callable=io.StringIO) as out:
                rc = cli._print_index_constituent_snap("^NSEI")
                txt = out.getvalue()
            self.assertEqual(rc, 0)
            self.assertIn("Snap: TEST INDEX", txt)
            self.assertIn("A.NS", txt)
            self.assertIn("B.NS", txt)
            self.assertIn("Range", txt)
            self.assertIn("[", txt)
            # Green rows first (D then A), then red rows by smallest fall first (C then B).
            self.assertLess(txt.index("D.NS"), txt.index("A.NS"))
            self.assertLess(txt.index("A.NS"), txt.index("C.NS"))
            self.assertLess(txt.index("C.NS"), txt.index("B.NS"))
            self.assertIn("Snap fetch passes used: 1", txt)
        finally:
            cli._SNAP_UNIVERSE_CACHE = old

        with patch("sys.stderr", new_callable=io.StringIO) as err:
            rc2 = cli._print_index_constituent_snap("^NOPE")
            self.assertEqual(rc2, 3)
            self.assertIn("Indian indices (except INDIA VIX) and DOW JONES", err.getvalue())

    @patch("tickertrail.cli._batch_index_snapshots")
    def test_print_index_constituent_snap_disables_nasdaq_even_when_configured(self, mock_snapshots):
        mock_snapshots.return_value = {
            "AAPL": {
                "regularMarketPrice": 200.0,
                "regularMarketPreviousClose": 195.0,
                "regularMarketDayLow": 190.0,
                "regularMarketDayHigh": 205.0,
            }
        }
        old = cli._SNAP_UNIVERSE_CACHE
        try:
            cli._SNAP_UNIVERSE_CACHE = {"^IXIC": ("NASDAQ", ("AAPL",))}
            with patch("sys.stderr", new_callable=io.StringIO) as err:
                rc = cli._print_index_constituent_snap("^IXIC")
                self.assertEqual(rc, 3)
                self.assertIn("Indian indices (except INDIA VIX) and DOW JONES", err.getvalue())
            mock_snapshots.assert_not_called()
        finally:
            cli._SNAP_UNIVERSE_CACHE = old

    @patch("tickertrail.cli._batch_index_snapshots")
    def test_print_index_constituent_snap_disables_other_global_indices_even_when_configured(self, mock_snapshots):
        mock_snapshots.return_value = {
            "AZN.L": {
                "regularMarketPrice": 120.0,
                "regularMarketPreviousClose": 118.0,
                "regularMarketDayLow": 117.0,
                "regularMarketDayHigh": 121.0,
            }
        }
        old = cli._SNAP_UNIVERSE_CACHE
        try:
            cli._SNAP_UNIVERSE_CACHE = {"^FTSE": ("FTSE 100", ("AZN.L",))}
            with patch("sys.stderr", new_callable=io.StringIO) as err:
                rc = cli._print_index_constituent_snap("^FTSE")
                self.assertEqual(rc, 3)
                self.assertIn("Indian indices (except INDIA VIX) and DOW JONES", err.getvalue())
            mock_snapshots.assert_not_called()
        finally:
            cli._SNAP_UNIVERSE_CACHE = old

    @patch("tickertrail.cli._fetch_group_snapshots_with_retries")
    def test_print_index_constituent_snap_falls_back_to_index_only_when_universe_missing(self, mock_fetch):
        mock_fetch.return_value = (
            {
                "^NSEMDCP50": {
                    "regularMarketPrice": 16653.5,
                    "regularMarketPreviousClose": 16772.4,
                    "regularMarketDayLow": 16548.95,
                    "regularMarketDayHigh": 16736.85,
                }
            },
            1,
        )
        old = cli._SNAP_UNIVERSE_CACHE
        try:
            cli._SNAP_UNIVERSE_CACHE = {}
            with patch("sys.stdout", new_callable=io.StringIO) as out, patch("sys.stderr", new_callable=io.StringIO) as err:
                rc = cli._print_index_constituent_snap("^NSEMDCP50")
            self.assertEqual(rc, 0)
            self.assertIn("Snap: NIFTY MIDCAP SELECT (index-only)", out.getvalue())
            self.assertIn("^NSEMDCP50", out.getvalue())
            self.assertIn("Constituent universe unavailable", err.getvalue())
        finally:
            cli._SNAP_UNIVERSE_CACHE = old

    @patch("tickertrail.cli._batch_index_snapshots", return_value={})
    def test_print_index_constituent_snap_incomplete_count_warning(self, _mock_snap):
        old = cli._SNAP_UNIVERSE_CACHE
        try:
            cli._SNAP_UNIVERSE_CACHE = {"^CNXMIDCAP": ("NIFTY MIDCAP 100", ("A.NS", "B.NS"))}
            with patch("sys.stdout", new_callable=io.StringIO) as out, patch("sys.stderr", new_callable=io.StringIO) as err:
                rc = cli._print_index_constituent_snap("^CNXMIDCAP")
                self.assertEqual(rc, 0)
                self.assertIn("configured / 100 expected", out.getvalue())
                self.assertIn("incomplete for NIFTY MIDCAP 100", err.getvalue())
        finally:
            cli._SNAP_UNIVERSE_CACHE = old

    @patch("tickertrail.cli._batch_index_snapshots", return_value={})
    def test_print_index_constituent_snap_incomplete_count_warning_for_alias_input(self, _mock_snap):
        old = cli._SNAP_UNIVERSE_CACHE
        try:
            cli._SNAP_UNIVERSE_CACHE = {"^CNXMIDCAP": ("NIFTY MIDCAP 100", ("A.NS", "B.NS"))}
            with patch("sys.stdout", new_callable=io.StringIO) as out, patch("sys.stderr", new_callable=io.StringIO) as err:
                rc = cli._print_index_constituent_snap("^NSEMDCP100")
                self.assertEqual(rc, 0)
                self.assertIn("configured / 100 expected", out.getvalue())
                self.assertIn("incomplete for NIFTY MIDCAP 100", err.getvalue())
        finally:
            cli._SNAP_UNIVERSE_CACHE = old

    @patch("tickertrail.cli._get_quote_payload")
    @patch("tickertrail.cli._batch_index_snapshots")
    def test_print_index_constituent_snap_three_pass_fallback(self, mock_batch, mock_get_quote):
        def _fake_batch(symbols):
            if symbols == ["A.NS", "B.NS"]:
                return {
                    "A.NS": {"regularMarketPrice": 101.0, "regularMarketPreviousClose": 100.0},
                    "B.NS": {"regularMarketPrice": None, "regularMarketPreviousClose": None},
                }
            if symbols == ["B.NS"]:
                return {"B.NS": {"regularMarketPrice": None, "regularMarketPreviousClose": None}}
            return {sym: {"regularMarketPrice": None, "regularMarketPreviousClose": None} for sym in symbols}

        mock_batch.side_effect = _fake_batch
        mock_get_quote.return_value = {
            "regularMarketPrice": 99.0,
            "regularMarketPreviousClose": 100.0,
            "regularMarketDayLow": 95.0,
            "regularMarketDayHigh": 102.0,
        }
        old = cli._SNAP_UNIVERSE_CACHE
        try:
            cli._SNAP_UNIVERSE_CACHE = {"^NSEI": ("TEST INDEX", ("A.NS", "B.NS"))}
            with patch("sys.stdout", new_callable=io.StringIO) as out:
                rc = cli._print_index_constituent_snap("^NSEI")
                txt = out.getvalue()
            self.assertEqual(rc, 0)
            self.assertIn("Snap fetch passes used: 3", txt)
            self.assertTrue(mock_get_quote.called)
        finally:
            cli._SNAP_UNIVERSE_CACHE = old

    def test_market_open_weekend_branch(self):
        class FakeDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return dt.datetime(2026, 2, 15, 10, 0, tzinfo=tz)  # Sunday

        with patch("tickertrail.cli.dt.datetime", FakeDateTime):
            self.assertFalse(cli._is_market_open_now("AAPL", {"currency": "USD"}))

    def test_print_rebased_table_trim_2y_monthly(self):
        dates = [f"{i:02d}-01-25" for i in range(1, 31)]
        stock = [100 + i for i in range(30)]
        bench = [100 + i / 2 for i in range(30)]
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            cli._print_rebased_table_output("X", "Y", "2y", "1mo", dates, stock, bench)
            txt = out.getvalue()
        self.assertIn("Date Range: 07-01-25 -> 30-01-25", txt)


class BranchRenderAndReplTests(unittest.TestCase):
    def test_build_multi_rebased_frame_guard_branches(self):
        tz = dt.timezone.utc
        t0 = dt.datetime(2026, 1, 1, tzinfo=tz)
        self.assertIsNone(cli._build_multi_rebased_frame([], tz, intraday=False))
        self.assertIsNone(cli._build_multi_rebased_frame([("X", [], [])], tz, intraday=False))
        self.assertIsNone(
            cli._build_multi_rebased_frame(
                [("X", [t0], [0.0]), ("Y", [t0], [1.0])],
                tz,
                intraday=False,
            )
        )

    def test_print_compare_table_output_trims_2y_monthly(self):
        idx = pd.date_range("2024-01-31", periods=30, freq="ME", tz="UTC")
        frame = pd.DataFrame(
            {
                "A": [100.0 + i for i in range(30)],
                "B": [100.0 + i * 0.5 for i in range(30)],
            },
            index=[int(ts.timestamp()) for ts in idx],
        )
        frame["date"] = pd.to_datetime(frame.index, unit="s", utc=True).strftime("%d-%m-%y")
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            cli._print_compare_table_output(["A", "B"], "2y", "1mo", frame)
            txt = out.getvalue()
        self.assertIn("Compare (base=100)", txt)
        self.assertIn("Final", txt)

    @patch("tickertrail.cli._build_multi_rebased_frame", return_value=None)
    @patch("tickertrail.cli._fetch_close_points_for_token", return_value=([dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)], [100.0]))
    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("X", {"regularMarketPrice": 1.0}))
    def test_render_compare_table_no_overlap_branch(self, _mock_resolve, _mock_fetch, _mock_frame):
        rc = cli._render_compare_table(["a", "b"], "1y", "1mo")
        self.assertEqual(rc, 3)

    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("X", None))
    def test_render_compare_table_resolve_error_branch(self, _mock_resolve):
        rc = cli._render_compare_table(["a", "b"], "1y", "1mo")
        self.assertEqual(rc, 3)

    @patch("tickertrail.cli._fetch_close_points_for_token", return_value=([], []))
    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("X", {"regularMarketPrice": 1.0}))
    def test_render_compare_table_no_data_branch(self, _mock_resolve, _mock_fetch):
        rc = cli._render_compare_table(["a", "b"], "1y", "1mo")
        self.assertEqual(rc, 3)

    @patch("tickertrail.cli._fetch_close_points_for_token")
    def test_render_table_error_branches(self, mock_fetch):
        # no benchmark
        t = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        mock_fetch.return_value = ([t], [1.0])
        rc = cli._render_rebased_table("X", None, None, None, "1y", "1mo")
        self.assertEqual(rc, 3)
        # no stock prices
        mock_fetch.return_value = ([], [])
        rc2 = cli._render_rebased_table("X", None, "^NSEI", "NIFTY 50", "1y", "1mo")
        self.assertEqual(rc2, 3)
        # benchmark empty
        mock_fetch.side_effect = [([t], [1.0]), ([], [])]
        rc3 = cli._render_rebased_table("X", None, "^NSEI", "NIFTY 50", "1y", "1mo")
        self.assertEqual(rc3, 3)

    @patch("tickertrail.cli._fetch_close_points_for_token", return_value=([], []))
    def test_draw_chart_error_branch(self, _mock_fetch):
        self.assertEqual(cli._draw_chart("X", "3m", "1d", 20, 80, None), 3)

    @patch("tickertrail.cli._fetch_close_points_for_token")
    def test_render_table_interval_error_and_no_overlap(self, mock_fetch):
        rc = cli._render_rebased_table("X", None, "^NSEI", "NIFTY 50", "6mo", "1m")
        self.assertEqual(rc, 3)
        t0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        t1 = dt.datetime(2026, 1, 2, tzinfo=dt.timezone.utc)
        mock_fetch.side_effect = [([t0], [100.0]), ([t1], [200.0])]
        rc2 = cli._render_rebased_table("X", None, "^NSEI", "NIFTY 50", "1y", "1mo")
        self.assertEqual(rc2, 3)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("X", None))
    def test_run_repl_no_active_symbol_errors(self, _mock_resolve, _mock_hist):
        cmds = ["t", "tt", "cc", "c", "1y", "r", "unknown", "exit"]
        with patch("builtins.input", side_effect=cmds), patch("sys.stderr", new_callable=io.StringIO):
            rc = cli._run_repl(None, None, None, 80, 20)
        self.assertEqual(rc, 0)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    def test_run_repl_eof_and_keyboard_interrupt(self, _mock_hist):
        with patch("builtins.input", side_effect=EOFError):
            self.assertEqual(cli._run_repl(None, None, None, 80, 20), 0)
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            self.assertEqual(cli._run_repl(None, None, None, 80, 20), 0)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    def test_run_repl_empty_command_continue(self, _mock_hist):
        with patch("builtins.input", side_effect=["", "exit"]):
            self.assertEqual(cli._run_repl(None, None, None, 80, 20), 0)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_code_matches", return_value=0)
    def test_run_repl_code_command(self, mock_code, _mock_hist):
        with patch("builtins.input", side_effect=["code national thermal", "exit"]):
            rc = cli._run_repl(None, None, None, 80, 20)
        self.assertEqual(rc, 0)
        mock_code.assert_called_once_with(" national thermal")

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_symbol_news", return_value=0)
    def test_run_repl_news_command(self, mock_news, _mock_hist):
        with (
            patch("builtins.input", side_effect=["news infy", "news", "exit"]),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = cli._run_repl(None, None, None, 80, 20)
        self.assertEqual(rc, 0)
        mock_news.assert_called_once_with("infy")
        self.assertIn("Usage: news <code>", err.getvalue())

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_watchlist_snapshot", return_value=0)
    @patch("tickertrail.cli._add_symbols_to_watchlist", return_value=(0, ["TCS.NS"], ["bad"], ["TCS.NS"]))
    @patch("tickertrail.cli._remove_symbols_from_watchlist", return_value=(0, ["TCS.NS"], ["MISS"]))
    @patch("tickertrail.cli._watchlist_symbols")
    @patch("tickertrail.cli._create_watchlist", return_value=(0, "Watchlist 'swing' created."))
    def test_run_repl_watchlist_alias_mode_add_and_snap(
        self,
        _mock_create,
        mock_watchlist_symbols,
        mock_remove_symbols,
        mock_add_symbols,
        mock_watch_snap,
        _mock_hist,
    ):
        def _watchlists(name):
            if name == "swing":
                return ["TCS.NS", "INFY.NS"]
            return None

        mock_watchlist_symbols.side_effect = _watchlists
        with patch("builtins.input", side_effect=["wl create swing", "wl swing", "list", "add tcs bad", "delete tcs miss", "snap", "watchlist", "exit"]), patch(
            "sys.stdout", new_callable=io.StringIO
        ) as out:
            rc = cli._run_repl(None, None, None, 80, 20)
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        mock_add_symbols.assert_called_once_with("swing", ["tcs", "bad"])
        mock_remove_symbols.assert_called_once_with("swing", ["tcs", "miss"])
        mock_watch_snap.assert_called_once_with("swing")
        self.assertIn("Already exists in swing: TCS.NS", txt)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._merge_watchlists", return_value=(0, "Watchlist 'combo' created by merging 'a' + 'b' (2 symbols)."))
    @patch("tickertrail.cli._watchlist_symbols")
    def test_run_repl_watchlist_merge_and_open(self, mock_watch_symbols, mock_merge, _mock_hist):
        mock_watch_symbols.side_effect = lambda name: ["TCS.NS"] if name == "combo" else None
        cmds = ["watchlist merge a b combo", "watchlist open combo", "watchlist", "exit"]
        with patch("builtins.input", side_effect=cmds), patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._run_repl(None, None, None, 80, 20)
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        mock_merge.assert_called_once_with("a", "b", "combo")
        self.assertIn("Watchlist mode exited.", txt)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._list_watchlists", return_value=["swing", "longterm"])
    @patch("tickertrail.cli._watchlist_symbols")
    def test_run_repl_watchlist_list(self, mock_watch_symbols, _mock_list, _mock_hist):
        mock_watch_symbols.side_effect = lambda name: ["TCS.NS"] if name == "swing" else ["INFY.NS", "RELIANCE.NS"]
        with patch("builtins.input", side_effect=["watchlist list", "exit"]), patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._run_repl(None, None, None, 80, 20)
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Watchlists:", txt)
        self.assertIn("swing (1 symbols)", txt)
        self.assertIn("longterm (2 symbols)", txt)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._list_watchlists", return_value=["swing"])
    @patch("tickertrail.cli._watchlist_symbols", return_value=["TCS.NS"])
    def test_run_repl_bare_wl_aliases_to_list(self, _mock_watch_symbols, _mock_list, _mock_hist):
        with patch("builtins.input", side_effect=["wl", "exit"]), patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._run_repl(None, None, None, 80, 20)
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Watchlists:", txt)
        self.assertIn("swing (1 symbols)", txt)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._watchlist_symbols", return_value=None)
    def test_run_repl_watchlist_missing_mode(self, _mock_symbols, _mock_hist):
        with patch("builtins.input", side_effect=["watchlist ghost", "exit"]), patch("sys.stderr", new_callable=io.StringIO) as err:
            rc = cli._run_repl(None, None, None, 80, 20)
        self.assertEqual(rc, 0)
        self.assertIn("not found", err.getvalue().lower())

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._list_watchlists", return_value=[])
    def test_run_repl_watchlist_usage_errors(self, _mock_list, _mock_hist):
        cmds = [
            "watchlist create",
            "watchlist list x",
            "watchlist delete",
            "watchlist merge a b",
            "watchlist open",
            "watchlist a b",
            "watchlist list",
            "exit",
        ]
        with patch("builtins.input", side_effect=cmds), patch("sys.stderr", new_callable=io.StringIO) as err, patch(
            "sys.stdout", new_callable=io.StringIO
        ) as out:
            rc = cli._run_repl(None, None, None, 80, 20)
            err_txt = err.getvalue()
            out_txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Usage: watchlist create <name>", err_txt)
        self.assertIn("Usage: watchlist list", err_txt)
        self.assertIn("Usage: watchlist delete <name>", err_txt)
        self.assertIn("Usage: watchlist merge <wl1> <wl2> <target>", err_txt)
        self.assertIn("Usage: watchlist open <name>", err_txt)
        self.assertIn("Usage: watchlist <name>", err_txt)
        self.assertIn("No watchlists found.", out_txt)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._watchlist_symbols")
    @patch("tickertrail.cli._remove_symbols_from_watchlist", side_effect=[(2, [], ["x"]), (0, [], [])])
    @patch("tickertrail.cli._add_symbols_to_watchlist", return_value=(2, [], ["x"], []))
    def test_run_repl_watchlist_add_delete_edge_paths(
        self,
        _mock_add,
        _mock_delete,
        mock_watch_symbols,
        _mock_hist,
    ):
        mock_watch_symbols.side_effect = lambda name: [] if name == "swing" else None
        cmds = ["watchlist swing", "list", "add", "add x", "delete", "delete x", "delete x", "watchlist", "add x", "exit"]
        with patch("builtins.input", side_effect=cmds), patch("sys.stderr", new_callable=io.StringIO) as err, patch(
            "sys.stdout", new_callable=io.StringIO
        ) as out:
            rc = cli._run_repl(None, None, None, 80, 20)
            err_txt = err.getvalue()
            out_txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("swing (0 symbols)", out_txt)
        self.assertIn("Usage: add <stock code>", err_txt)
        self.assertIn("Watchlist 'swing' not found.", err_txt)
        self.assertIn("Usage: delete <stock code>", err_txt)
        self.assertIn("No symbols deleted.", out_txt)
        self.assertIn("`add` is available only in watchlist mode.", err_txt)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    def test_run_repl_r_no_active_and_index_list(self, _mock_hist):
        with patch("builtins.input", side_effect=["r", "index list", "exit"]), patch("sys.stderr", new_callable=io.StringIO):
            rc = cli._run_repl(None, None, None, 80, 20)
        self.assertEqual(rc, 0)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_index_constituent_snap", return_value=0)
    @patch("tickertrail.cli._print_quote", return_value=0)
    def test_run_repl_snap_active_index(self, _mock_quote, mock_snap, _mock_hist):
        with patch("builtins.input", side_effect=["snap", "exit"]):
            rc = cli._run_repl("^NSEI", "^NSEI", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, 80, 20)
        self.assertEqual(rc, 0)
        mock_snap.assert_called_once_with("^NSEI")

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_index_constituent_snap", return_value=0)
    @patch("tickertrail.cli._print_quote", return_value=0)
    def test_run_repl_prompt_fragment_then_snap(self, _mock_quote, mock_snap, _mock_hist):
        with patch("builtins.input", side_effect=["tickertrail>cnxit> snap", "exit"]):
            rc = cli._run_repl("^CNXIT", "^CNXIT", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, 80, 20)
        self.assertEqual(rc, 0)
        mock_snap.assert_called_once_with("^CNXIT")

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._resolve_symbol", return_value=("^CNXMNC", {"regularMarketPrice": 1.0}))
    @patch("tickertrail.cli._print_quote", return_value=0)
    def test_run_repl_index_mode_alias_switch_path(self, _mock_quote, _mock_resolve_symbol, _mock_hist):
        with patch("builtins.input", side_effect=["mnc", "exit"]):
            rc = cli._run_repl("^CNXINFRA", "^CNXINFRA", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, 80, 20)
        self.assertEqual(rc, 0)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._index_quote_fallback_payload", return_value={"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0})
    @patch("tickertrail.cli._resolve_symbol", return_value=("^CNXMNC", None))
    @patch("tickertrail.cli._print_quote", return_value=0)
    def test_run_repl_index_mode_alias_switch_uses_snapshot_fallback(
        self,
        mock_quote,
        _mock_resolve_symbol,
        mock_fallback,
        _mock_hist,
    ):
        with patch("builtins.input", side_effect=["mnc", "exit"]), patch("sys.stderr", new_callable=io.StringIO) as err:
            rc = cli._run_repl("^CNXINFRA", "^CNXINFRA", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, 80, 20)
        self.assertEqual(rc, 0)
        mock_fallback.assert_called_once_with("^CNXMNC")
        self.assertGreaterEqual(mock_quote.call_count, 2)
        switched_call = mock_quote.call_args_list[-1]
        self.assertEqual(switched_call.args[1], "^CNXMNC")
        self.assertNotIn("quote unavailable", err.getvalue().lower())

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    def test_run_repl_prints_network_footer(self, _mock_hist):
        with patch("builtins.input", side_effect=["h", "exit"]), patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._run_repl(None, None, None, 80, 20)
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Network calls: 0 [none] | cache: hits=0 misses=0", txt)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli.subprocess.run", return_value=None)
    def test_run_repl_shell_passthrough_and_empty_usage(self, mock_shell, _mock_hist):
        with (
            patch("builtins.input", side_effect=["!", "!pwd", "exit"]),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = cli._run_repl(None, None, None, 80, 20)
        self.assertEqual(rc, 0)
        self.assertIn("Usage: !<shell-cmd>", err.getvalue())
        mock_shell.assert_called_once_with("pwd", shell=True, check=False)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    def test_run_repl_snap_no_active_symbol(self, _mock_hist):
        with patch("builtins.input", side_effect=["snap", "exit"]), patch("sys.stderr", new_callable=io.StringIO) as err:
            rc = cli._run_repl(None, None, None, 80, 20)
        self.assertEqual(rc, 0)
        self.assertIn("Enter an index symbol first", err.getvalue())

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=0)
    @patch("tickertrail.cli._resolve_benchmark_for_table", return_value=("B", "Bench", "bench error"))
    def test_run_repl_t_benchmark_error(self, _mock_bench, _mock_quote, _mock_hist):
        with patch("builtins.input", side_effect=["t", "exit"]), patch("sys.stderr", new_callable=io.StringIO):
            rc = cli._run_repl("BEL", "BEL.NS", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, 80, 20)
        self.assertEqual(rc, 0)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=0)
    def test_run_repl_tt_usage_errors(self, _mock_quote, _mock_hist):
        cmds = ["tt a mo", "tt a b c", "exit"]
        with patch("builtins.input", side_effect=cmds), patch("sys.stderr", new_callable=io.StringIO):
            rc = cli._run_repl("BEL", "BEL.NS", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, 80, 20)
        self.assertEqual(rc, 0)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._render_compare_table", return_value=0)
    @patch("tickertrail.cli._print_quote", return_value=0)
    def test_run_repl_comp_usage_error_then_success(self, _mock_quote, mock_comp, _mock_hist):
        cmds = ["cmp nifty w", "cmp nifty goldbees 3y w", "exit"]
        with patch("builtins.input", side_effect=cmds), patch("sys.stderr", new_callable=io.StringIO) as err:
            rc = cli._run_repl("BEL", "BEL.NS", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, 80, 20)
        self.assertEqual(rc, 0)
        self.assertIn("Usage: cmp", err.getvalue())
        self.assertEqual(mock_comp.call_count, 1)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=0)
    @patch("tickertrail.cli._resolve_benchmark_override", return_value=(None, "bench error"))
    def test_run_repl_cc_and_c_benchmark_errors(self, _mock_bench, _mock_quote, _mock_hist):
        cmds = ["cc x", "c x", "exit"]
        with patch("builtins.input", side_effect=cmds), patch("sys.stderr", new_callable=io.StringIO):
            rc = cli._run_repl("BEL", "BEL.NS", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, 80, 20)
        self.assertEqual(rc, 0)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=0)
    def test_run_repl_parse_errors_t_cc_c(self, _mock_quote, _mock_hist):
        cmds = ["t - 3m", "cc x mo", "c - 3m", "exit"]
        with patch("builtins.input", side_effect=cmds), patch("sys.stderr", new_callable=io.StringIO):
            rc = cli._run_repl("BEL", "BEL.NS", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, 80, 20)
        self.assertEqual(rc, 0)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=0)
    @patch("tickertrail.cli._resolve_benchmark_override", return_value=(None, None))
    @patch("tickertrail.cli._resolve_benchmark_for_table", return_value=(None, None, None))
    @patch("tickertrail.cli._draw_chart", return_value=0)
    @patch("tickertrail.cli._render_rebased_table", return_value=0)
    def test_run_repl_canonical_chart_table_routes(
        self,
        mock_table,
        mock_chart,
        _mock_resolve_table,
        _mock_resolve_chart,
        _mock_quote,
        _mock_hist,
    ):
        cmds = ["chart swing 1y", "chart intra 5m", "table swing 6mo", "table intra 15m", "exit"]
        with patch("builtins.input", side_effect=cmds):
            rc = cli._run_repl("BEL", "BEL.NS", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, 80, 20)
        self.assertEqual(rc, 0)
        self.assertGreaterEqual(mock_chart.call_count, 2)
        self.assertGreaterEqual(mock_table.call_count, 2)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    def test_run_repl_help_topic_and_unknown_topic(self, _mock_hist):
        with (
            patch("builtins.input", side_effect=["help chart", "help badtopic", "exit"]),
            patch("sys.stdout", new_callable=io.StringIO) as out,
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = cli._run_repl(None, None, None, 80, 20)
            out_txt = out.getvalue()
            err_txt = err.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Chart Commands:", out_txt)
        self.assertIn("Unknown help topic", err_txt)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    def test_run_repl_help_topics_and_canonical_usage_errors(self, _mock_hist):
        cmds = ["help core", "help index", "help table", "help watchlist", "table", "table bad", "chart", "chart bad", "exit"]
        with (
            patch("builtins.input", side_effect=cmds),
            patch("sys.stdout", new_callable=io.StringIO) as out,
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = cli._run_repl(None, None, None, 80, 20)
            out_txt = out.getvalue()
            err_txt = err.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Core Commands:", out_txt)
        self.assertIn("Index Commands:", out_txt)
        self.assertIn("Table Commands:", out_txt)
        self.assertIn("Watchlist Commands:", out_txt)
        self.assertIn("Usage: table <swing|intra> ...", err_txt)
        self.assertIn("Usage: chart <swing|intra> ...", err_txt)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    def test_run_repl_help_command_details(self, _mock_hist):
        cmds = ["help move", "help watchlist open", "help corr", "exit"]
        with (
            patch("builtins.input", side_effect=cmds),
            patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            rc = cli._run_repl(None, None, None, 80, 20)
            out_txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Command: move", out_txt)
        self.assertIn("Aliases: moves", out_txt)
        self.assertIn("Defaults:", out_txt)
        self.assertIn("period: 1mo", out_txt)
        self.assertIn("Command: watchlist open", out_txt)
        self.assertIn("Command: corr", out_txt)
        self.assertIn("Examples:", out_txt)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    def test_run_repl_help_command_details_exhaustive(self, _mock_hist):
        cmds = [
            "help help",
            "help q",
            "help cls",
            "help cache",
            "help cache clear",
            "help reload",
            "help r",
            "help !",
            "help code",
            "help news",
            "help index",
            "help index list",
            "help snap",
            "help move",
            "help trend",
            "help relret",
            "help corr",
            "help cmp",
            "help chart",
            "help chart swing",
            "help chart intra",
            "help c",
            "help cc",
            "help table",
            "help table swing",
            "help table intra",
            "help t",
            "help tt",
            "help watchlist",
            "help watchlist create",
            "help watchlist list",
            "help watchlist open",
            "help watchlist delete",
            "help watchlist merge",
            "help add",
            "help delete",
            "help list",
            "help <period>",
            "help <symbol>",
            "exit",
        ]
        with (
            patch("builtins.input", side_effect=cmds),
            patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            rc = cli._run_repl(None, None, None, 80, 20)
            out_txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Command: help", out_txt)
        self.assertIn("Command: news", out_txt)
        self.assertIn("Command: chart swing", out_txt)
        self.assertIn("Command: table intra", out_txt)
        self.assertIn("Command: watchlist merge", out_txt)
        self.assertIn("Command: <period>", out_txt)
        self.assertIn("Command: <symbol>", out_txt)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._watchlist_symbols")
    @patch("tickertrail.cli._delete_watchlist", return_value=(0, "Watchlist 'swing' deleted."))
    @patch("tickertrail.cli._add_symbols_to_watchlist", return_value=(0, [], [], []))
    def test_run_repl_watchlist_edge_paths_for_new_branches(
        self,
        _mock_add,
        _mock_delete,
        mock_watchlist_symbols,
        _mock_hist,
    ):
        state = {"calls": 0}

        def _watch_symbols(name):
            if name != "swing":
                return None
            state["calls"] += 1
            if state["calls"] == 1:
                return ["TCS.NS"]
            return None

        mock_watchlist_symbols.side_effect = _watch_symbols
        cmds = ["watchlist ", "watchlist open swing", "list", "add tcs", "watchlist delete swing", "exit"]
        with (
            patch("builtins.input", side_effect=cmds),
            patch("sys.stdout", new_callable=io.StringIO) as out,
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = cli._run_repl(None, None, None, 80, 20)
            out_txt = out.getvalue()
            err_txt = err.getvalue()
        self.assertEqual(rc, 0)
        self.assertNotIn("Watchlist mode exited.", out_txt)
        self.assertIn("Watchlist 'swing' not found.", err_txt)
        self.assertIn("No new symbols added.", out_txt)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=0)
    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("BEL.NS", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}))
    @patch("tickertrail.cli._watchlist_symbols", return_value=["TCS.NS"])
    def test_run_repl_symbol_switch_exits_watchlist_mode(
        self,
        _mock_watch_symbols,
        _mock_resolve_symbol,
        _mock_quote,
        _mock_hist,
    ):
        cmds = ["watchlist open swing", "bel", "add tcs", "exit"]
        with (
            patch("builtins.input", side_effect=cmds),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = cli._run_repl(None, None, None, 80, 20)
            err_txt = err.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("`add` is available only in watchlist mode.", err_txt)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=2)
    def test_run_repl_initial_quote_failure_returns_code(self, _mock_quote, _mock_hist):
        rc = cli._run_repl("BEL", "BEL.NS", {"regularMarketPrice": 1.0}, 80, 20)
        self.assertEqual(rc, 2)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._parse_intraday_command_args", return_value=(None, "err"))
    @patch("tickertrail.cli._print_quote", return_value=0)
    def test_run_repl_tt_default_intraday_parse_error(self, _mock_quote, _mock_parse, _mock_hist):
        with patch("builtins.input", side_effect=["tt", "exit"]), patch("sys.stderr", new_callable=io.StringIO):
            rc = cli._run_repl("BEL", "BEL.NS", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, 80, 20)
        self.assertEqual(rc, 0)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=0)
    @patch("tickertrail.cli._resolve_benchmark_for_table", return_value=(None, None, "bench error"))
    def test_run_repl_tt_benchmark_error(self, _mock_resolve_bench, _mock_quote, _mock_hist):
        with patch("builtins.input", side_effect=["tt", "exit"]), patch("sys.stderr", new_callable=io.StringIO):
            rc = cli._run_repl("BEL", "BEL.NS", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, 80, 20)
        self.assertEqual(rc, 0)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=0)
    @patch("tickertrail.cli._get_quote_payload", return_value={"regularMarketPrice": 102.0, "regularMarketPreviousClose": 100.0})
    @patch("tickertrail.cli._has_quote_data", return_value=True)
    def test_run_repl_quote_and_q_alias(self, _mock_has, mock_get_quote, mock_print_quote, _mock_hist):
        with patch("builtins.input", side_effect=["q", "quote", "exit"]):
            rc = cli._run_repl("BEL", "BEL.NS", {"regularMarketPrice": 101.0, "regularMarketPreviousClose": 100.0}, 80, 20)
        self.assertEqual(rc, 0)
        self.assertEqual(mock_get_quote.call_count, 2)
        self.assertGreaterEqual(mock_print_quote.call_count, 3)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._watchlist_symbols", return_value=["BEL.NS"])
    @patch("tickertrail.cli._get_quote_payload")
    def test_run_repl_quote_blocked_in_watchlist_mode(self, mock_get_quote, _mock_watch_symbols, _mock_hist):
        with (
            patch("builtins.input", side_effect=["watchlist open swing", "quote", "watchlist", "exit"]),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = cli._run_repl(None, None, None, 80, 20)
        self.assertEqual(rc, 0)
        self.assertIn("unavailable in watchlist mode", err.getvalue().lower())
        self.assertEqual(mock_get_quote.call_count, 0)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=0)
    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("BEL.NS", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}))
    @patch("tickertrail.cli._watchlist_symbols", return_value=["INFY.NS"])
    @patch("tickertrail.cli._add_symbols_to_watchlist", return_value=(0, ["TCS.NS"], [], []))
    def test_run_repl_cd_dotdot_restores_watchlist_mode(
        self,
        mock_add,
        _mock_watch_symbols,
        mock_resolve_symbol,
        _mock_quote,
        _mock_hist,
    ):
        with patch("builtins.input", side_effect=["watchlist open swing", "bel", "cd ..", "add tcs", "exit"]):
            rc = cli._run_repl(None, None, None, 80, 20)
        self.assertEqual(rc, 0)
        self.assertEqual(mock_resolve_symbol.call_count, 1)
        self.assertEqual(mock_add.call_count, 1)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=0)
    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("BEL.NS", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}))
    def test_run_repl_cd_dotdot_restores_index_mode(self, mock_resolve_symbol, mock_quote, _mock_hist):
        with patch("builtins.input", side_effect=["bel", "cd ..", "exit"]):
            rc = cli._run_repl("CNXIT", "^CNXIT", {"regularMarketPrice": 2.0, "regularMarketPreviousClose": 2.0}, 80, 20)
        self.assertEqual(rc, 0)
        self.assertEqual(mock_resolve_symbol.call_count, 1)
        self.assertGreaterEqual(mock_quote.call_count, 3)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    def test_run_repl_cd_dotdot_without_target(self, _mock_hist):
        with (
            patch("builtins.input", side_effect=["cd ..", "exit"]),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = cli._run_repl(None, None, None, 80, 20)
        self.assertEqual(rc, 0)
        self.assertIn("No previous index/watchlist mode", err.getvalue())

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=0)
    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("BEL.NS", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}))
    def test_run_repl_cd_dotdot_watchlist_missing_on_restore(self, mock_resolve_symbol, _mock_quote, _mock_hist):
        with (
            patch("tickertrail.cli._watchlist_symbols", side_effect=[["INFY.NS"], None]),
            patch("builtins.input", side_effect=["watchlist open swing", "bel", "cd ..", "exit"]),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = cli._run_repl(None, None, None, 80, 20)
        self.assertEqual(rc, 0)
        self.assertEqual(mock_resolve_symbol.call_count, 1)
        self.assertIn("Watchlist 'swing' not found.", err.getvalue())

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=0)
    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("BEL.NS", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}))
    @patch("tickertrail.cli._has_quote_data", return_value=False)
    def test_run_repl_cd_dotdot_index_restore_without_cached_quote(self, _mock_has, _mock_resolve_symbol, _mock_quote, _mock_hist):
        with (
            patch("builtins.input", side_effect=["bel", "cd ..", "exit"]),
            patch("sys.stdout", new_callable=io.StringIO) as out,
        ):
            rc = cli._run_repl("CNXIT", "^CNXIT", {}, 80, 20)
        self.assertEqual(rc, 0)
        self.assertIn("Use `quote` to refresh quote", out.getvalue())

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    def test_run_repl_quote_usage_and_no_active_symbol_errors(self, _mock_hist):
        with (
            patch("builtins.input", side_effect=["quote x", "quote", "exit"]),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = cli._run_repl(None, None, None, 80, 20)
        self.assertEqual(rc, 0)
        err_txt = err.getvalue()
        self.assertIn("Usage: quote", err_txt)
        self.assertIn("No active symbol. Enter a symbol first.", err_txt)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=0)
    @patch("tickertrail.cli._index_quote_fallback_payload", return_value=None)
    @patch("tickertrail.cli._has_quote_data", return_value=False)
    @patch("tickertrail.cli._get_quote_payload", return_value={})
    def test_run_repl_quote_index_refresh_failure(self, _mock_get, _mock_has, _mock_fallback, _mock_quote, _mock_hist):
        with (
            patch("builtins.input", side_effect=["quote", "exit"]),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = cli._run_repl("CNXIT", "^CNXIT", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, 80, 20)
        self.assertEqual(rc, 0)
        self.assertIn("Could not fetch quote for '^CNXIT'.", err.getvalue())

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._resolve_symbol", return_value=("^CNXMNC", None))
    @patch("tickertrail.cli._index_quote_fallback_payload", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=0)
    def test_run_repl_index_alias_switch_quote_unavailable(self, _mock_quote, _mock_fallback, _mock_resolve, _mock_hist):
        with (
            patch("builtins.input", side_effect=["mnc", "exit"]),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = cli._run_repl("CNXIT", "^CNXIT", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, 80, 20)
        self.assertEqual(rc, 0)
        self.assertIn("quote unavailable", err.getvalue().lower())

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._index_quote_fallback_payload", return_value=None)
    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("^CNXIT", None))
    @patch("tickertrail.cli._print_quote", return_value=0)
    def test_run_repl_symbol_switch_index_resolution_still_missing_quote(self, _mock_quote, _mock_resolve, _mock_fallback, _mock_hist):
        with (
            patch("builtins.input", side_effect=["^CNXIT", "exit"]),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = cli._run_repl("BEL", "BEL.NS", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, 80, 20)
        self.assertEqual(rc, 0)
        self.assertIn("Could not fetch quote for '^CNXIT'.", err.getvalue())

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._resolve_benchmark_override", return_value=(None, None))
    @patch("tickertrail.cli._parse_intraday_command_args", return_value=(cli._ParsedIntradayCommand(interval="5m"), None))
    @patch("tickertrail.cli._draw_chart", return_value=0)
    @patch("tickertrail.cli._print_quote", return_value=0)
    @patch("tickertrail.cli._get_quote_payload", return_value={"regularMarketPrice": 102.0, "regularMarketPreviousClose": 100.0})
    @patch("tickertrail.cli._has_quote_data", return_value=True)
    def test_run_repl_r_replays_intraday_view(
        self,
        _mock_has_data,
        _mock_get_quote,
        _mock_print_quote,
        mock_draw,
        _mock_parse_intraday,
        _mock_resolve_bench,
        _mock_hist,
    ):
        with patch("builtins.input", side_effect=["cc", "r", "exit"]):
            rc = cli._run_repl("BEL", "BEL.NS", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, 80, 20)
        self.assertEqual(rc, 0)
        self.assertGreaterEqual(mock_draw.call_count, 2)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=0)
    @patch("tickertrail.cli._get_quote_payload", return_value={})
    @patch("tickertrail.cli._has_quote_data", return_value=False)
    def test_run_repl_r_refresh_failure(self, _mock_has, _mock_get, _mock_quote, _mock_hist):
        with patch("builtins.input", side_effect=["r", "exit"]), patch("sys.stderr", new_callable=io.StringIO):
            rc = cli._run_repl("BEL", "BEL.NS", {"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}, 80, 20)
        self.assertEqual(rc, 0)

    @patch("tickertrail.cli._run_repl", return_value=0)
    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("AAPL", {"regularMarketPrice": 1.0}))
    def test_main_plain_symbol_path(self, _mock_resolve, mock_repl):
        rc = cli.main(["AAPL"])
        self.assertEqual(rc, 0)
        self.assertTrue(mock_repl.called)


if __name__ == "__main__":
    unittest.main()
