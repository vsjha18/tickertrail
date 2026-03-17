import io
import unittest
from unittest.mock import patch

from tickertrail.cli import _run_repl


def _run_repl_session(*commands: str) -> int:
    """Run one REPL session for cache-command tests with the provided inputs."""
    with patch("builtins.input", side_effect=list(commands)):
        return _run_repl(
            start_input_symbol=None,
            start_resolved_symbol=None,
            start_info=None,
            width=100,
            height=22,
        )


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
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            rc = _run_repl_session("cache", "exit")
        txt = out.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("History Cache Summary", txt)
        self.assertIn("Entries: 3 total (3 parsed keys)", txt)
        self.assertIn("Kinds: close_points=2, daily_ohlcv=1", txt)
        self.assertIn("Symbols (2): INFY.NS, TCS.NS", txt)

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    @patch("tickertrail.cli.price_history.clear_history_cache_today")
    def test_cache_clear_reports_result_state(self, mock_clear, _mock_history) -> None:
        """REPL cache clear command should distinguish deleted vs already-empty states."""
        cases = (
            (True, "Cleared today's history cache."),
            (False, "Today's history cache is already empty."),
        )
        for deleted, expected in cases:
            with self.subTest(deleted=deleted):
                mock_clear.return_value = deleted
                with patch("sys.stdout", new_callable=io.StringIO) as out:
                    rc = _run_repl_session("cache clear", "exit")
                self.assertEqual(rc, 0)
                self.assertIn(expected, out.getvalue())

    @patch("tickertrail.cli._enable_repl_history", return_value=None)
    def test_cache_command_rejects_unknown_subcommand(self, _mock_history) -> None:
        """REPL should keep cache command grammar explicit for unsupported subcommands."""
        with (
            patch("sys.stderr", new_callable=io.StringIO) as err,
        ):
            rc = _run_repl_session("cache foo", "exit")
        self.assertEqual(rc, 0)
        self.assertIn("Usage: cache | cache clear", err.getvalue())


if __name__ == "__main__":
    unittest.main()
