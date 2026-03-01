import io
import unittest
from unittest.mock import patch

from tickertrail.cli import _run_repl


class CacheCommandTests(unittest.TestCase):
    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli.price_history.history_cache_summary_today")
    def test_cache_reports_summary(self, mock_summary, _mock_history) -> None:
        """REPL cache command should print a compact summary of today's cache contents."""
        mock_summary.return_value = {
            "day": "2026-03-01",
            "path": ".cache/history/2026-03-01.json",
            "file_exists": True,
            "file_size_bytes": 4321,
            "entries_total": 3,
            "entries_parsed": 3,
            "kinds": {"close_points": 2, "daily_ohlcv": 1},
            "symbols": ["INFY.NS", "TCS.NS"],
            "periods": ["1mo", "1y"],
            "intervals": ["1d"],
        }
        with patch("builtins.input", side_effect=["cache", "exit"]), patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = _run_repl(
                start_input_symbol=None,
                start_resolved_symbol=None,
                start_info=None,
                width=100,
                height=22,
            )
        txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("History Cache Summary", txt)
        self.assertIn("Entries: 3 total (3 parsed keys)", txt)
        self.assertIn("Kinds: close_points=2, daily_ohlcv=1", txt)
        self.assertIn("Symbols (2): INFY.NS, TCS.NS", txt)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli.price_history.clear_history_cache_today", return_value=True)
    def test_cache_clear_reports_deleted(self, _mock_clear, _mock_history) -> None:
        """REPL cache clear command should confirm deletion when a cache file existed."""
        with patch("builtins.input", side_effect=["cache clear", "exit"]), patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = _run_repl(
                start_input_symbol=None,
                start_resolved_symbol=None,
                start_info=None,
                width=100,
                height=22,
            )
        self.assertEqual(rc, 0)
        self.assertIn("Cleared today's history cache.", out.getvalue())

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli.price_history.clear_history_cache_today", return_value=False)
    def test_cache_clear_reports_empty(self, _mock_clear, _mock_history) -> None:
        """REPL cache clear command should report when today's cache is already empty."""
        with patch("builtins.input", side_effect=["cache clear", "exit"]), patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = _run_repl(
                start_input_symbol=None,
                start_resolved_symbol=None,
                start_info=None,
                width=100,
                height=22,
            )
        self.assertEqual(rc, 0)
        self.assertIn("Today's history cache is already empty.", out.getvalue())

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    def test_cache_usage_for_unknown_subcommand(self, _mock_history) -> None:
        """REPL should keep cache command grammar explicit for unsupported subcommands."""
        with (
            patch("builtins.input", side_effect=["cache foo", "exit"]),
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = _run_repl(
                start_input_symbol=None,
                start_resolved_symbol=None,
                start_info=None,
                width=100,
                height=22,
            )
        self.assertEqual(rc, 0)
        self.assertIn("Usage: cache | cache clear", err.getvalue())


if __name__ == "__main__":
    unittest.main()
