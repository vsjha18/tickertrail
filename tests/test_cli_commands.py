import datetime as dt
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

import tickertrail.cli as cli


def _mk_df(index, close, low=None, high=None):
    data = {"Close": close}
    if low is not None:
        data["Low"] = low
    if high is not None:
        data["High"] = high
    return pd.DataFrame(data, index=pd.DatetimeIndex(index))


class HelperCoverageTests(unittest.TestCase):
    def test_basic_formatters_and_colors(self):
        self.assertIn(cli._color_by_sign(1.0), {"green", "red"})
        self.assertEqual(cli._color_by_sign(0.0), "gray")
        self.assertEqual(cli._fmt_price(None), "n/a")
        self.assertEqual(cli._fmt_change(None, None), "n/a")
        self.assertTrue(cli._fmt_compact_num(10_000).endswith("K"))
        self.assertIn("[", cli._range_line(10, 20, 15, width=12))

    def test_parser_build(self):
        p = cli._build_parser()
        args = p.parse_args(["AAPL", "chart", "--period", "1y", "--interval", "1wk"])
        self.assertEqual(args.symbol, "AAPL")
        self.assertEqual(args.command, "chart")
        self.assertEqual(args.period, "1y")
        self.assertEqual(args.interval, "1wk")

    def test_candidate_and_period_normalizers(self):
        self.assertEqual(cli._candidate_symbols("reliance")[0], "RELIANCE.NS")
        self.assertEqual(cli._candidate_symbols("^NSEI"), ["^NSEI"])
        self.assertEqual(cli._candidate_symbols("nifty"), ["^NSEI"])
        self.assertEqual(cli._candidate_symbols("it"), ["^CNXIT"])
        self.assertEqual(cli._candidate_symbols("metals"), ["^CNXMETAL"])
        self.assertEqual(cli._candidate_symbols("consumer"), ["^CNXCONSUM"])
        self.assertEqual(cli._candidate_symbols("dow"), ["^DJI"])
        self.assertEqual(cli._normalize_period_token("3mo"), "3mo")
        self.assertIsNone(cli._normalize_period_token("3m"))
        self.assertEqual(cli._period_token_days("2y"), 730)
        self.assertEqual(cli._normalize_agg_token("w"), "1wk")
        self.assertIsNone(cli._normalize_agg_token("2w"))

    def test_interval_and_profile_helpers(self):
        self.assertEqual(cli._interval_minutes("5m"), 5)
        self.assertIsNone(cli._interval_minutes("x"))
        tz, oh, om, ch, cm = cli._market_profile_for("RELIANCE.NS", {"currency": "INR"})
        self.assertEqual((oh, om, ch, cm), (9, 15, 15, 30))
        self.assertEqual(str(tz), "Asia/Kolkata")
        self.assertEqual(cli._prompt_for_symbol("BEL.NS"), "tickertrail>bel> ")
        self.assertEqual(cli._prompt_for_symbol("^NSEI"), "tickertrail>nsei> ")

    @patch("tickertrail.cli.yf.Ticker")
    def test_get_quote_payload_merge_and_fallbacks(self, mock_ticker):
        t = MagicMock()
        t.fast_info = {"lastPrice": 10, "previousClose": 9, "open": 9.5, "dayLow": 9.1, "dayHigh": 10.1, "volume": 100}
        t.info = {"shortName": "X"}
        mock_ticker.return_value = t
        out = cli._get_quote_payload("X")
        self.assertEqual(out["regularMarketPrice"], 10)
        self.assertEqual(out["regularMarketPreviousClose"], 9)
        self.assertEqual(out["regularMarketOpen"], 9.5)
        self.assertEqual(out["regularMarketDayLow"], 9.1)
        self.assertEqual(out["regularMarketDayHigh"], 10.1)
        self.assertEqual(out["regularMarketVolume"], 100)
        self.assertEqual(out["shortName"], "X")

    @patch("tickertrail.cli._get_quote_payload")
    def test_resolve_symbol_paths(self, mock_payload):
        mock_payload.side_effect = [
            {},  # RELIANCE.NS
            {"regularMarketPrice": 1.0},  # RELIANCE.BO
        ]
        sym, info = cli._resolve_symbol("reliance")
        self.assertEqual(sym, "RELIANCE.BO")
        self.assertIsNotNone(info)

    def test_load_nse_universe_and_search(self):
        with tempfile.TemporaryDirectory() as td:
            csv_path = Path(td) / "nse.csv"
            csv_path.write_text("SYMBOL,NAME OF COMPANY\nSBIN,STATE BANK OF INDIA\nBEL,BHARAT ELECTRONICS LTD\n", encoding="utf-8")
            old = cli._NSE_UNIVERSE_CSV
            old_cache = cli._NSE_UNIVERSE_CACHE
            try:
                cli._NSE_UNIVERSE_CACHE = None
                cli._NSE_UNIVERSE_CSV = csv_path
                rows = cli._load_nse_universe()
                self.assertEqual(len(rows), 2)
                options = cli._search_symbol_options("bank")
                self.assertTrue(any("SBIN.NS" == o["symbol"] for o in options))
            finally:
                cli._NSE_UNIVERSE_CSV = old
                cli._NSE_UNIVERSE_CACHE = old_cache

    @patch("tickertrail.cli.yf.Ticker")
    @patch("tickertrail.cli._resolve_symbol_with_fallback")
    def test_print_symbol_news_success(self, mock_resolve, mock_ticker_cls):
        mock_resolve.return_value = ("INFY.NS", {"regularMarketPrice": 1.0})
        ticker = MagicMock()
        ticker.news = [
            {
                "title": "Infosys announces new AI platform",
                "publisher": "Reuters",
                "providerPublishTime": 1_706_000_000,
                "link": "https://example.com/news-1",
            }
        ]
        mock_ticker_cls.return_value = ticker
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_symbol_news("infy")
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("News: INFY.NS", txt)
        self.assertIn("Infosys announces new AI platform", txt)
        self.assertIn("https://example.com/news-1", txt)
        self.assertRegex(txt, r"\(\d+[mhd] ago\)")

    @patch("tickertrail.cli.views.print_quote", return_value=0)
    @patch("tickertrail.cli._fetch_daily_ohlcv_for_period", return_value=([], [], [], [], []))
    def test_print_quote_overrides_known_index_short_name_with_canonical_label(self, _mock_ohlcv, mock_print_quote):
        info = {"shortName": "NIFTY MIDCAP 50", "regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0}
        rc = cli._print_quote("^NSEMDCP50", "^NSEMDCP50", include_after_hours=True, preloaded_info=info)
        self.assertEqual(rc, 0)
        passed_info = mock_print_quote.call_args.kwargs["preloaded_info"]
        self.assertIsInstance(passed_info, dict)
        self.assertEqual(passed_info["shortName"], "NIFTY MIDCAP SELECT")

    @patch("tickertrail.cli.yf.Ticker")
    @patch("tickertrail.cli._resolve_symbol_with_fallback")
    def test_print_symbol_news_no_items(self, mock_resolve, mock_ticker_cls):
        mock_resolve.return_value = ("INFY.NS", {"regularMarketPrice": 1.0})
        ticker = MagicMock()
        ticker.news = []
        mock_ticker_cls.return_value = ticker
        with patch("sys.stderr", new_callable=io.StringIO) as err:
            rc = cli._print_symbol_news("infy")
        self.assertEqual(rc, 2)
        self.assertIn("No Yahoo news found", err.getvalue())

    def test_news_publish_timestamp_paths(self):
        self.assertIsNotNone(cli._news_publish_timestamp({"providerPublishTime": 1_706_000_000}))
        self.assertIsNotNone(cli._news_publish_timestamp({"providerPublishTime": 1_706_000_000_000}))
        # Oversized timestamp should hit exception guard and return None.
        self.assertIsNone(cli._news_publish_timestamp({"providerPublishTime": 1e20}))
        self.assertIsNotNone(cli._news_publish_timestamp({"publishedAt": "2026-02-24T10:30:00Z"}))
        self.assertIsNotNone(cli._news_publish_timestamp({"pubDate": "2026-02-24T10:30:00Z"}))
        self.assertIsNone(cli._news_publish_timestamp({"publishedAt": ""}))
        self.assertIsNone(cli._news_publish_timestamp({"publishedAt": "not-a-date"}))
        self.assertIsNone(cli._news_publish_timestamp({}))

    @patch("tickertrail.cli._resolve_symbol_with_fallback")
    def test_print_symbol_news_usage_and_unresolved(self, mock_resolve):
        with patch("sys.stderr", new_callable=io.StringIO) as err:
            rc_usage = cli._print_symbol_news("")
        self.assertEqual(rc_usage, 2)
        self.assertIn("Usage: news <code>", err.getvalue())

        mock_resolve.return_value = ("INFY.NS", None)
        with patch("sys.stderr", new_callable=io.StringIO) as err:
            rc_unresolved = cli._print_symbol_news("infy")
        self.assertEqual(rc_unresolved, 2)
        self.assertIn("Could not resolve symbol", err.getvalue())

    @patch("tickertrail.cli.yf.Ticker", side_effect=RuntimeError("network down"))
    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("INFY.NS", {"regularMarketPrice": 1.0}))
    def test_print_symbol_news_ticker_exception(self, _mock_resolve, _mock_ticker):
        with patch("sys.stderr", new_callable=io.StringIO) as err:
            rc = cli._print_symbol_news("infy")
        self.assertEqual(rc, 2)
        self.assertIn("No Yahoo news found", err.getvalue())

    @patch("tickertrail.cli.yf.Ticker")
    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("INFY.NS", {"regularMarketPrice": 1.0}))
    def test_print_symbol_news_filters_invalid_items(self, _mock_resolve, mock_ticker_cls):
        ticker = MagicMock()
        ticker.news = ["bad", {"title": ""}, {"publisher": "Reuters"}]
        mock_ticker_cls.return_value = ticker
        with patch("sys.stderr", new_callable=io.StringIO) as err:
            rc = cli._print_symbol_news("infy")
        self.assertEqual(rc, 2)
        self.assertIn("No Yahoo news found", err.getvalue())

    @patch("tickertrail.cli.yf.Ticker")
    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("INFY.NS", {"regularMarketPrice": 1.0}))
    def test_print_symbol_news_limit_and_link_optional(self, _mock_resolve, mock_ticker_cls):
        ticker = MagicMock()
        ticker.news = [
            {"title": "Headline one", "publishedAt": "2026-02-24T10:30:00Z"},
            {"title": "Headline two", "link": "https://example.com/news-2"},
        ]
        mock_ticker_cls.return_value = ticker
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_symbol_news("infy", limit=1)
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Headline one", txt)
        self.assertNotIn("Headline two", txt)

    @patch("tickertrail.cli.yf.Ticker")
    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("INFY.NS", {"regularMarketPrice": 1.0}))
    def test_print_symbol_news_falls_back_to_get_news(self, _mock_resolve, mock_ticker_cls):
        ticker = MagicMock()
        ticker.news = []
        ticker.get_news.return_value = [{"title": "Fallback headline", "publisher": "Yahoo"}]
        mock_ticker_cls.return_value = ticker
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_symbol_news("infy")
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Fallback headline", txt)

    @patch("tickertrail.cli.yf.Ticker")
    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("INFY.NS", {"regularMarketPrice": 1.0}))
    def test_print_symbol_news_parses_wrapped_content_payload(self, _mock_resolve, mock_ticker_cls):
        ticker = MagicMock()
        ticker.news = []
        ticker.get_news.return_value = [
            {
                "content": {
                    "headline": "Wrapped headline",
                    "publisher": "Reuters",
                    "canonicalUrl": {"url": "https://example.com/wrapped"},
                    "publishedAt": "2026-02-24T10:30:00Z",
                }
            }
        ]
        mock_ticker_cls.return_value = ticker
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_symbol_news("infy")
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Wrapped headline", txt)
        self.assertIn("https://example.com/wrapped", txt)

    @patch("tickertrail.cli.yf.Ticker")
    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("INFY.NS", {"regularMarketPrice": 1.0}))
    def test_print_symbol_news_uses_outer_timestamp_when_content_lacks_it(self, _mock_resolve, mock_ticker_cls):
        ticker = MagicMock()
        ticker.news = [
            {
                "providerPublishTime": 1_706_000_000,
                "content": {
                    "headline": "Outer-time headline",
                    "canonicalUrl": {"url": "https://example.com/outer-time"},
                },
            }
        ]
        mock_ticker_cls.return_value = ticker
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_symbol_news("infy")
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Outer-time headline", txt)
        self.assertIn("ago", txt)

    @patch("tickertrail.cli.yf.Ticker")
    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("INFY.NS", {"regularMarketPrice": 1.0}))
    def test_print_symbol_news_sorts_newest_first_when_timestamp_available(self, _mock_resolve, mock_ticker_cls):
        ticker = MagicMock()
        ticker.news = [
            {"title": "Older headline", "providerPublishTime": 1_705_900_000},
            {"title": "Newest headline", "providerPublishTime": 1_706_100_000},
        ]
        mock_ticker_cls.return_value = ticker
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_symbol_news("infy")
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertLess(txt.index("Newest headline"), txt.index("Older headline"))

    def test_watchlist_crud_and_add_symbols(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "db.json"
            old_db = cli._WATCHLIST_DB_JSON
            try:
                cli._WATCHLIST_DB_JSON = db_path
                rc_create, msg_create = cli._create_watchlist("swing")
                self.assertEqual(rc_create, 0)
                self.assertIn("created", msg_create.lower())
                self.assertEqual(cli._list_watchlists(), ["swing"])
                self.assertEqual(cli._watchlist_symbols("swing"), [])

                with patch("tickertrail.cli._validate_watchlist_symbol", side_effect=["TCS.NS", None, "INFY.NS", "TCS.NS"]):
                    rc_add, added, rejected, existing = cli._add_symbols_to_watchlist("swing", ["tcs", "bad", "infy", "tcs"])
                self.assertEqual(rc_add, 0)
                self.assertEqual(added, ["TCS.NS", "INFY.NS"])
                self.assertEqual(rejected, ["bad"])
                self.assertEqual(existing, ["TCS.NS"])
                self.assertEqual(cli._watchlist_symbols("swing"), ["TCS.NS", "INFY.NS"])

                rc_rm, removed, missing = cli._remove_symbols_from_watchlist("swing", ["TCS", "xyz"])
                self.assertEqual(rc_rm, 0)
                self.assertEqual(removed, ["TCS.NS"])
                self.assertEqual(missing, ["xyz"])
                self.assertEqual(cli._watchlist_symbols("swing"), ["INFY.NS"])

                rc_del, msg_del = cli._delete_watchlist("swing")
                self.assertEqual(rc_del, 0)
                self.assertIn("deleted", msg_del.lower())
                self.assertEqual(cli._list_watchlists(), [])
            finally:
                cli._WATCHLIST_DB_JSON = old_db

    def test_watchlist_helpers_branch_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "db.json"
            old_db = cli._WATCHLIST_DB_JSON
            try:
                cli._WATCHLIST_DB_JSON = db_path
                self.assertEqual(cli._load_watchlists(), {})
                self.assertFalse(cli._watchlist_name_valid("bad name"))
                self.assertFalse(cli._watchlist_name_valid(""))

                db_path.write_text('{"watchlists":{"x":["AAPL", 1, "AAPL", " "]}}', encoding="utf-8")
                self.assertEqual(cli._load_watchlists(), {"x": ["AAPL"]})

                rc_bad, _msg_bad = cli._create_watchlist("bad name")
                self.assertEqual(rc_bad, 2)
                rc_ok, _msg_ok = cli._create_watchlist("core")
                self.assertEqual(rc_ok, 0)
                rc_dup, _msg_dup = cli._create_watchlist("core")
                self.assertEqual(rc_dup, 2)

                rc_del_missing, _msg_del_missing = cli._delete_watchlist("none")
                self.assertEqual(rc_del_missing, 2)

                rc_merge_missing, _msg_merge_missing = cli._merge_watchlists("none", "core", "combo")
                self.assertEqual(rc_merge_missing, 2)

                rc_merge_bad_name, _msg_merge_bad_name = cli._merge_watchlists("core", "core", "bad name")
                self.assertEqual(rc_merge_bad_name, 2)

                rc_second_ok, _msg_second_ok = cli._create_watchlist("growth")
                self.assertEqual(rc_second_ok, 0)
                with patch("tickertrail.cli._validate_watchlist_symbol", side_effect=["TCS.NS", "INFY.NS", "RELIANCE.NS"]):
                    rc_add_core, *_ = cli._add_symbols_to_watchlist("core", ["tcs", "infy"])
                    rc_add_growth, *_ = cli._add_symbols_to_watchlist("growth", ["reliance"])
                self.assertEqual(rc_add_core, 0)
                self.assertEqual(rc_add_growth, 0)

                rc_merge_create, msg_merge_create = cli._merge_watchlists("core", "growth", "combo")
                self.assertEqual(rc_merge_create, 0)
                self.assertIn("created", msg_merge_create)
                self.assertEqual(cli._watchlist_symbols("combo"), ["TCS.NS", "INFY.NS", "RELIANCE.NS"])

                rc_merge_update, msg_merge_update = cli._merge_watchlists("growth", "core", "combo")
                self.assertEqual(rc_merge_update, 0)
                self.assertIn("updated", msg_merge_update)
                self.assertEqual(cli._watchlist_symbols("combo"), ["TCS.NS", "INFY.NS", "RELIANCE.NS"])

                with patch("tickertrail.cli._load_nse_universe", return_value=[]):
                    self.assertIsNone(cli._validate_watchlist_symbol("tcs"))
                with patch("tickertrail.cli._load_nse_universe", return_value=[{"symbol": "TCS", "name": "TCS LTD"}]):
                    self.assertEqual(cli._validate_watchlist_symbol("tcs"), "TCS.NS")
                    self.assertEqual(cli._validate_watchlist_symbol("TCS.NS"), "TCS.NS")
                    self.assertEqual(cli._validate_watchlist_symbol("TCS.BO"), "TCS.NS")

                rc_missing, added_missing, rejected_missing, existing_missing = cli._add_symbols_to_watchlist("none", ["TCS"])
                self.assertEqual((rc_missing, added_missing, rejected_missing, existing_missing), (2, [], ["TCS"], []))
                rc_rm_missing, removed_missing, not_present = cli._remove_symbols_from_watchlist("none", ["TCS"])
                self.assertEqual((rc_rm_missing, removed_missing, not_present), (2, [], ["TCS"]))
            finally:
                cli._WATCHLIST_DB_JSON = old_db

    def test_print_watchlist_snapshot_paths(self):
        with patch("tickertrail.cli._watchlist_symbols", return_value=None), patch("sys.stderr", new_callable=io.StringIO) as err:
            rc = cli._print_watchlist_snapshot("x")
            self.assertEqual(rc, 3)
            self.assertIn("not found", err.getvalue().lower())

        with patch("tickertrail.cli._watchlist_symbols", return_value=[]), patch("sys.stderr", new_callable=io.StringIO) as err:
            rc = cli._print_watchlist_snapshot("x")
            self.assertEqual(rc, 3)
            self.assertIn("empty", err.getvalue().lower())

        with patch("tickertrail.cli._watchlist_symbols", return_value=["TCS.NS"]), patch(
            "tickertrail.cli._fetch_group_snapshots_with_retries",
            return_value=(
                {
                    "TCS.NS": {"regularMarketPrice": 10.0, "regularMarketPreviousClose": 9.0, "regularMarketDayLow": 9.0, "regularMarketDayHigh": 10.0},
                    "^NSEI": {"regularMarketPrice": 22100.0, "regularMarketPreviousClose": 22000.0},
                },
                2,
            ),
        ), patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_watchlist_snapshot("x")
            self.assertEqual(rc, 0)
            self.assertIn("Symbol", out.getvalue())
            self.assertIn("Equal-Weight 1D", out.getvalue())
            self.assertIn("NIFTY 50 1D", out.getvalue())
            self.assertIn("Alpha", out.getvalue())

        with patch("tickertrail.cli._watchlist_symbols", return_value=["X.NS"]), patch(
            "tickertrail.cli._fetch_group_snapshots_with_retries",
            return_value=(
                {"X.NS": {"regularMarketPrice": "bad", "regularMarketPreviousClose": None, "regularMarketDayLow": "bad", "regularMarketDayHigh": 10.0}},
                1,
            ),
        ), patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_watchlist_snapshot("x")
            self.assertEqual(rc, 0)
            self.assertIn("n/a", out.getvalue())
            self.assertIn("Equal-Weight 1D  n/a", out.getvalue())

        with patch("tickertrail.cli._watchlist_symbols", return_value=["A.NS", "B.NS", "C.NS"]), patch(
            "tickertrail.cli._fetch_group_snapshots_with_retries",
            return_value=(
                {
                    "A.NS": {"regularMarketPrice": 110.0, "regularMarketPreviousClose": 100.0, "regularMarketDayLow": 95.0, "regularMarketDayHigh": 112.0},
                    "B.NS": {"regularMarketPrice": 98.0, "regularMarketPreviousClose": 100.0, "regularMarketDayLow": 96.0, "regularMarketDayHigh": 101.0},
                    "C.NS": {"regularMarketPrice": 99.5, "regularMarketPreviousClose": 100.0, "regularMarketDayLow": 98.0, "regularMarketDayHigh": 100.5},
                    "^NSEI": {"regularMarketPrice": 22050.0, "regularMarketPreviousClose": 22000.0},
                },
                1,
            ),
        ), patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_watchlist_snapshot("x")
            txt = out.getvalue()
            self.assertEqual(rc, 0)
            self.assertLess(txt.index("A.NS"), txt.index("C.NS"))
            self.assertLess(txt.index("C.NS"), txt.index("B.NS"))
            row_lines = [line for line in txt.splitlines() if line.startswith(("A.NS", "B.NS", "C.NS"))]
            self.assertTrue(len(set(len(line) for line in row_lines)) == 1)
            self.assertIn("Equal-Weight 1D", txt)

    @patch("tickertrail.cli._search_symbol_options")
    def test_print_code_matches_success_and_no_match(self, mock_search):
        mock_search.side_effect = [
            [{"symbol": "NTPC.NS", "name": "NTPC LTD", "exchange": "NSE", "type": "EQUITY"}],
            [],
        ]
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_code_matches("national thermal")
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("NTPC.NS", txt)
        with patch("sys.stderr", new_callable=io.StringIO) as err:
            rc2 = cli._print_code_matches("zzz")
        self.assertEqual(rc2, 2)
        self.assertIn("No code matches found", err.getvalue())

    @patch("sys.stdin.isatty", return_value=False)
    def test_choose_symbol_non_tty(self, _mock_tty):
        out = cli._choose_symbol_from_options("bank", [{"symbol": "SBIN.NS", "name": "STATE BANK", "exchange": "NSE", "type": "EQUITY"}])
        self.assertEqual(out, "SBIN.NS")

    @patch("sys.stdin.isatty", return_value=True)
    def test_choose_symbol_tty_prompt(self, _mock_tty):
        opts = [
            {"symbol": "SBIN.NS", "name": "STATE BANK", "exchange": "NSE", "type": "EQUITY"},
            {"symbol": "BANKBARODA.NS", "name": "BANK OF BARODA", "exchange": "NSE", "type": "EQUITY"},
        ]
        with patch("builtins.input", side_effect=["9", "2"]):
            out = cli._choose_symbol_from_options("bank", opts)
        self.assertEqual(out, "BANKBARODA.NS")

    @patch("tickertrail.cli._resolve_symbol")
    @patch("tickertrail.cli._search_symbol_options")
    @patch("tickertrail.cli._choose_symbol_from_options")
    def test_resolve_with_fallback(self, mock_choose, mock_search, mock_resolve):
        mock_resolve.side_effect = [("X", None), ("SBIN.NS", {"regularMarketPrice": 1})]
        mock_search.return_value = [{"symbol": "SBIN.NS"}]
        mock_choose.return_value = "SBIN.NS"
        sym, info = cli._resolve_symbol_with_fallback("sbinx")
        self.assertEqual(sym, "SBIN.NS")
        self.assertIsNotNone(info)

    @patch("tickertrail.cli.yf.download")
    def test_fetch_close_points_and_range_fallback(self, mock_download):
        idx = [pd.Timestamp("2026-02-16 09:15:00", tz="UTC"), pd.Timestamp("2026-02-16 09:20:00", tz="UTC")]
        mock_download.return_value = _mk_df(idx, [10.0, 11.0], low=[9.5, 10.5], high=[10.5, 11.5])
        pts, prices = cli._fetch_close_points_for_token("X", "1d", "5m")
        self.assertEqual(len(pts), 2)
        self.assertEqual(prices[-1], 11.0)
        lo, hi = cli._fetch_day_range_fallback("X")
        self.assertEqual((lo, hi), (9.5, 11.5))

    def test_table_and_chart_interval_policy(self):
        self.assertEqual(cli._table_interval_for_period_token("2y"), "1mo")
        self.assertEqual(cli._interval_for_chart_period("2y"), "1wk")
        self.assertIsNotNone(cli._validate_period_interval("3m", "1d"))
        self.assertIsNotNone(cli._validate_period_interval("3mo", "1m"))

    def test_build_rebased_frame_and_table_output(self):
        tz = dt.timezone.utc
        s_pts = [dt.datetime(2026, 1, 1, tzinfo=tz), dt.datetime(2026, 2, 1, tzinfo=tz)]
        b_pts = [dt.datetime(2026, 1, 1, tzinfo=tz), dt.datetime(2026, 2, 1, tzinfo=tz)]
        df = cli._build_rebased_frame(s_pts, [100.0, 120.0], b_pts, [50.0, 60.0], dt.timezone.utc, intraday=False)
        self.assertIsNotNone(df)
        assert df is not None
        self.assertEqual(df["date"].tolist()[0], "01-01-26")
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            cli._print_rebased_table_output(
                symbol="X",
                benchmark_label="Y",
                period_token="1y",
                interval="1mo",
                dates=["01-01-26", "01-02-26"],
                stock_values=[100.0, 120.0],
                bench_values=[100.0, 110.0],
            )
            txt = out.getvalue()
        self.assertIn("Alpha%", txt)
        self.assertIn("Final Alpha%", txt)
        intraday_dates = [f"{9 + (i // 12):02d}:{(i % 12) * 5:02d}" for i in range(80)]
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            cli._print_rebased_table_output(
                symbol="X",
                benchmark_label="Y",
                period_token="1d",
                interval="5m",
                dates=intraday_dates,
                stock_values=[100.0 + i * 0.1 for i in range(80)],
                bench_values=[100.0 + i * 0.08 for i in range(80)],
            )
            intraday_txt = out.getvalue()
        self.assertIn("Sampled every", intraday_txt)
        self.assertIn("base interval: 5m", intraday_txt)

    def test_build_multi_rebased_frame_and_compare_output(self):
        tz = dt.timezone.utc
        t0 = dt.datetime(2026, 1, 1, tzinfo=tz)
        t1 = dt.datetime(2026, 2, 1, tzinfo=tz)
        frame = cli._build_multi_rebased_frame(
            series_by_symbol=[
                ("^NSEI", [t0, t1], [100.0, 110.0]),
                ("GOLDBEES.NS", [t0, t1], [50.0, 60.0]),
                ("HDFCBANK.NS", [t0, t1], [200.0, 210.0]),
            ],
            tz=dt.timezone.utc,
            intraday=False,
        )
        self.assertIsNotNone(frame)
        assert frame is not None
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            cli._print_compare_table_output(
                resolved_symbols=["^NSEI", "GOLDBEES.NS", "HDFCBANK.NS"],
                period_token="1y",
                interval="1mo",
                frame=frame,
            )
            txt = out.getvalue()
        self.assertIn("Compare (base=100)", txt)
        self.assertNotIn("Delta", txt)
        self.assertNotIn("Alpha%", txt)


class RenderCoverageTests(unittest.TestCase):
    @patch("tickertrail.cli.plt")
    @patch("tickertrail.cli._benchmark_symbol_for", return_value=("^NSEI", "NIFTY 50"))
    @patch("tickertrail.cli._fetch_close_points_for_token")
    def test_draw_chart_swing_with_benchmark(self, mock_fetch, _mock_bench, mock_plt):
        t0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        t1 = dt.datetime(2026, 2, 1, tzinfo=dt.timezone.utc)
        mock_fetch.side_effect = [
            ([t0, t1], [100.0, 120.0]),  # stock
            ([t0, t1], [200.0, 220.0]),  # bench
        ]
        rc = cli._draw_chart("BEL.NS", "1y", "1mo", 20, 100, info={"currency": "INR"})
        self.assertEqual(rc, 0)
        self.assertTrue(mock_plt.plot.called)
        self.assertTrue(mock_plt.show.called)

    @patch("tickertrail.cli.plt")
    @patch("tickertrail.cli._benchmark_symbol_for", return_value=("^NSEI", "NIFTY 50"))
    @patch("tickertrail.cli._fetch_close_points_for_token")
    def test_draw_chart_intraday_with_extend(self, mock_fetch, _mock_bench, mock_plt):
        t0 = dt.datetime(2026, 2, 16, 9, 15, tzinfo=dt.timezone.utc)
        t1 = dt.datetime(2026, 2, 16, 9, 20, tzinfo=dt.timezone.utc)
        mock_fetch.side_effect = [
            ([t0, t1], [100.0, 101.0]),
            ([t0, t1], [200.0, 201.0]),
        ]
        rc = cli._draw_chart("BEL.NS", "1d", "5m", 20, 100, info={"currency": "INR"})
        self.assertEqual(rc, 0)
        self.assertTrue(mock_plt.xticks.called)

    @patch("tickertrail.cli.plt")
    @patch("tickertrail.cli._benchmark_symbol_for", return_value=("^NSEI", "NIFTY 50"))
    @patch("tickertrail.cli._fetch_close_points_for_token")
    def test_draw_chart_does_not_print_rebased_table_block(self, mock_fetch, _mock_bench, _mock_plt):
        t0 = dt.datetime(2026, 2, 16, 9, 30, tzinfo=dt.timezone.utc)
        t1 = dt.datetime(2026, 2, 16, 9, 45, tzinfo=dt.timezone.utc)
        t2 = dt.datetime(2026, 2, 16, 10, 0, tzinfo=dt.timezone.utc)
        mock_fetch.side_effect = [
            ([t0, t1, t2], [100.0, 101.0, 102.0]),  # stock
            ([t0, t1], [200.0, 201.0]),  # benchmark ends earlier
        ]
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._draw_chart("BEL.NS", "1d", "5m", 20, 100, info={"currency": "INR"})
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Move:", txt)
        self.assertIn("From: 15:00 -> 15:30", txt)
        self.assertNotIn("Rebased Co-Plot (base=100)", txt)

    @patch("tickertrail.cli._fetch_close_points_for_token", return_value=([], []))
    def test_draw_chart_no_data(self, _mock_fetch):
        rc = cli._draw_chart("X", "1y", "1mo", 20, 100, info=None)
        self.assertEqual(rc, 3)

    @patch("tickertrail.cli.plt")
    @patch("tickertrail.cli._benchmark_symbol_for", return_value=(None, None))
    @patch("tickertrail.cli._fetch_close_points_for_token")
    def test_draw_chart_prints_52w_range_when_quote_fields_present(self, mock_fetch, _mock_bench, _mock_plt):
        t0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        t1 = dt.datetime(2026, 2, 1, tzinfo=dt.timezone.utc)
        mock_fetch.return_value = ([t0, t1], [100.0, 120.0])
        info = {"fiftyTwoWeekLow": 80.0, "fiftyTwoWeekHigh": 140.0}
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._draw_chart("BEL.NS", "1y", "1mo", 20, 100, info=info)
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("52W Range", txt)
        self.assertNotIn("52W Line:", txt)

    @patch("tickertrail.cli._fetch_close_points_for_token")
    def test_render_rebased_table_success_and_error(self, mock_fetch):
        t0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        t1 = dt.datetime(2026, 2, 1, tzinfo=dt.timezone.utc)
        mock_fetch.side_effect = [
            ([t0, t1], [100.0, 120.0]),
            ([t0, t1], [200.0, 220.0]),
        ]
        rc = cli._render_rebased_table("BEL.NS", {"currency": "INR"}, "^NSEI", "NIFTY 50", "1y", "1mo")
        self.assertEqual(rc, 0)

        mock_fetch.side_effect = [([], [])]
        rc2 = cli._render_rebased_table("BEL.NS", {"currency": "INR"}, "^NSEI", "NIFTY 50", "1y", "1mo")
        self.assertEqual(rc2, 3)

    @patch("tickertrail.cli._fetch_close_points_for_token")
    @patch("tickertrail.cli._resolve_symbol_with_fallback")
    def test_render_compare_table_success(self, mock_resolve, mock_fetch):
        tz = dt.timezone.utc
        t0 = dt.datetime(2026, 1, 1, tzinfo=tz)
        t1 = dt.datetime(2026, 2, 1, tzinfo=tz)
        mock_resolve.side_effect = [
            ("^NSEI", {"regularMarketPrice": 1.0}),
            ("GOLDBEES.NS", {"regularMarketPrice": 1.0}),
            ("HDFCBANK.NS", {"regularMarketPrice": 1.0}),
        ]
        mock_fetch.side_effect = [
            ([t0, t1], [100.0, 110.0]),
            ([t0, t1], [50.0, 60.0]),
            ([t0, t1], [200.0, 210.0]),
        ]
        rc = cli._render_compare_table(["nifty", "goldbees", "hdfcbank"], "3y", "1wk")
        self.assertEqual(rc, 0)

    @patch("tickertrail.cli._get_quote_payload")
    @patch("tickertrail.cli._has_quote_data", return_value=True)
    @patch("tickertrail.cli._fetch_day_range_fallback", return_value=(10.0, 12.0))
    @patch("tickertrail.cli._batch_index_snapshots", return_value={})
    def test_index_board_and_catalog(self, _mock_batch, _mock_rng, _mock_has, mock_q):
        mock_q.return_value = {"regularMarketPrice": 11.0, "regularMarketPreviousClose": 10.0}
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_index_board()
            self.assertEqual(rc, 0)
            self.assertIn("India", out.getvalue())
            self.assertIn("NIFTY INFRA", out.getvalue())
            self.assertIn("NIFTY NEXT 50", out.getvalue())
            self.assertIn("NIFTY MIDCAP SELECT", out.getvalue())
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc2 = cli._print_index_catalog()
            self.assertEqual(rc2, 0)
            self.assertIn("Index Catalog", out.getvalue())
            self.assertIn("NIFTY INFRA", out.getvalue())
            self.assertIn("NIFTY SMALLCAP 100", out.getvalue())
            self.assertIn("NIFTY MIDCAP SELECT", out.getvalue())

    @patch("tickertrail.cli._fetch_day_range_fallback", return_value=(None, None))
    @patch("tickertrail.cli._get_quote_payload", return_value={})
    @patch("tickertrail.cli._has_quote_data", return_value=False)
    @patch("tickertrail.cli._batch_index_snapshots")
    @patch("tickertrail.cli._colorize")
    def test_index_board_highlights_nifty_50_primary_columns(self, mock_colorize, mock_batch, _mock_has, _mock_quote, _mock_rng):
        mock_batch.return_value = {
            "^NSEI": {
                "regularMarketPrice": 99.0,
                "regularMarketPreviousClose": 100.0,
                "regularMarketDayLow": 98.0,
                "regularMarketDayHigh": 101.0,
            }
        }
        mock_colorize.side_effect = lambda text, color: f"[{color}]{text}[/{color}]"
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_index_board()
        self.assertEqual(rc, 0)
        self.assertIn("[cyan]NIFTY 50[/cyan]", out.getvalue())
        self.assertIn("[cyan]^NSEI[/cyan]", out.getvalue())
        self.assertIn("[cyan]99.00[/cyan]", out.getvalue())

    @patch("tickertrail.cli._fetch_day_range_fallback", return_value=(None, None))
    @patch("tickertrail.cli._get_quote_payload", return_value={})
    @patch("tickertrail.cli._has_quote_data", return_value=False)
    @patch("tickertrail.cli._batch_index_snapshots")
    def test_index_board_sorted_greens_then_reds(self, mock_batch, _mock_has, _mock_quote, _mock_rng):
        mock_batch.return_value = {
            "^NSEI": {
                "regularMarketPrice": 99.0,
                "regularMarketPreviousClose": 100.0,
                "regularMarketDayLow": 98.0,
                "regularMarketDayHigh": 101.0,
            },
            "^NSEBANK": {
                "regularMarketPrice": 101.0,
                "regularMarketPreviousClose": 100.0,
                "regularMarketDayLow": 99.0,
                "regularMarketDayHigh": 102.0,
            },
            "^CNXIT": {
                "regularMarketPrice": 104.0,
                "regularMarketPreviousClose": 100.0,
                "regularMarketDayLow": 98.0,
                "regularMarketDayHigh": 106.0,
            },
        }
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = cli._print_index_board()
            txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertLess(txt.index("NIFTY IT"), txt.index("NIFTY BANK"))
        self.assertLess(txt.index("NIFTY BANK"), txt.index("NIFTY 50"))

    @patch("tickertrail.cli._fetch_day_range_fallback")
    def test_fetch_day_range_fallback_candidates_tries_canonical_after_resolved(self, mock_rng):
        mock_rng.side_effect = [(None, None), (10.0, 12.0)]
        low, high = cli._fetch_day_range_fallback_candidates(["NIFTY_NEXT_50.NS", "^NIFTYNXT50"])
        self.assertEqual((low, high), (10.0, 12.0))
        self.assertEqual(mock_rng.call_args_list[0].args[0], "NIFTY_NEXT_50.NS")
        self.assertEqual(mock_rng.call_args_list[1].args[0], "^NIFTYNXT50")

    def test_extend_intraday_to_close_and_market_open(self):
        tz = dt.timezone.utc
        pts = [dt.datetime(2026, 2, 16, 9, 15, tzinfo=tz)]
        prices = [100.0]
        out_pts, out_prices = cli._extend_intraday_to_close(pts, prices, "5m", "BEL.NS", {"currency": "INR"})
        self.assertGreaterEqual(len(out_pts), 1)
        self.assertEqual(len(out_pts), len(out_prices))
        self.assertIsInstance(cli._is_market_open_now("AAPL", {"currency": "USD"}), bool)


class MainAndReplCoverageTests(unittest.TestCase):
    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli._print_quote", return_value=0)
    @patch("tickertrail.cli._render_compare_table", return_value=0)
    @patch("tickertrail.cli._render_rebased_table", return_value=0)
    @patch("tickertrail.cli._draw_chart", return_value=0)
    @patch("tickertrail.cli._resolve_benchmark_for_table", return_value=("^NSEI", "NIFTY 50", None))
    @patch("tickertrail.cli._resolve_benchmark_override", return_value=(None, None))
    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("INFY.NS", {"regularMarketPrice": 1.0}))
    @patch("tickertrail.cli._get_quote_payload", return_value={"regularMarketPrice": 1.0, "regularMarketPreviousClose": 1.0})
    @patch("tickertrail.cli._has_quote_data", return_value=True)
    @patch("tickertrail.cli.subprocess.run", return_value=None)
    def test_run_repl_large_command_sweep(
        self,
        _mock_subprocess,
        _mock_has,
        _mock_getq,
        _mock_resolve_symbol,
        _mock_resolve_bench_override,
        _mock_resolve_bench_table,
        _mock_draw,
        _mock_render,
        _mock_compare,
        _mock_print_quote,
        _mock_hist,
    ):
        cmds = [
            "h",
            "cls",
            "clear",
            "!pwd",
            "reload",
            "index",
            "index list",
            "t",
            "tt",
            "tt 15m",
            "tt sbin",
            "tt sbin 5m",
            "tt - 2y mo",
            "t nifty 3mo w",
            "cmp nifty goldbees hdfcbank 3y w",
            "cc",
            "cc 1m",
            "c",
            "c 2y",
            "c nifty 3mo w",
            "1y",
            "r",
            "foo",
            "exit",
        ]
        with patch("builtins.input", side_effect=cmds):
            rc = cli._run_repl(
                start_input_symbol="BEL",
                start_resolved_symbol="BEL.NS",
                start_info={"regularMarketPrice": 100.0, "regularMarketPreviousClose": 99.0},
                width=100,
                height=20,
            )
        self.assertEqual(rc, 0)

    @patch("tickertrail.cli._run_repl", return_value=0)
    @patch("tickertrail.cli._resolve_symbol_with_fallback", return_value=("AAPL", {"regularMarketPrice": 1.0}))
    @patch("tickertrail.cli._print_quote", return_value=0)
    @patch("tickertrail.cli._draw_chart", return_value=0)
    def test_main_modes(self, mock_draw, mock_quote, _mock_resolve, mock_repl):
        self.assertEqual(cli.main([]), 0)
        self.assertEqual(cli.main(["AAPL", "quote"]), 0)
        self.assertEqual(cli.main(["AAPL", "chart"]), 0)
        self.assertTrue(mock_repl.called)
        self.assertTrue(mock_quote.called)
        self.assertTrue(mock_draw.called)


if __name__ == "__main__":
    unittest.main()
