import io
import unittest
from unittest.mock import patch

from tickertrail.cli import _run_repl


class CacheCommandTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
