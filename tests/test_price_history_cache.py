import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from tickertrail import price_history


def _sample_df() -> pd.DataFrame:
    """Build a deterministic daily OHLCV frame for cache tests."""
    index = pd.DatetimeIndex([
        dt.datetime(2026, 2, 20),
        dt.datetime(2026, 2, 21),
    ])
    return pd.DataFrame(
        {
            "Close": [100.0, 101.0],
            "High": [101.0, 102.0],
            "Low": [99.0, 100.0],
            "Volume": [1_000_000.0, 1_200_000.0],
        },
        index=index,
    )


class DailyHistoryCacheTests(unittest.TestCase):
    def test_resolve_cache_dir_prefers_repo_root_from_cwd_ancestors(self) -> None:
        """Cache directory should resolve to repo root when cwd is inside a repo tree."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td) / "repo"
            nested = root / "tools" / "scripts"
            module_file = Path(td) / "site-packages" / "tickertrail" / "price_history.py"
            (root / "src" / "tickertrail").mkdir(parents=True)
            (root / "pyproject.toml").write_text("[project]\nname='tickertrail'\n", encoding="utf-8")
            nested.mkdir(parents=True)
            module_file.parent.mkdir(parents=True)
            module_file.write_text("# stub\n", encoding="utf-8")

            resolved = price_history._resolve_cache_dir(module_file=module_file, cwd=nested)
            self.assertEqual(resolved, (root / ".cache" / "history").resolve())

    def test_resolve_cache_dir_uses_module_tree_when_cwd_is_not_repo(self) -> None:
        """Cache directory should fall back to module repo when cwd has no repo markers."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            root = Path(td) / "repo"
            cwd = Path(td) / "scratch"
            module_file = root / "src" / "tickertrail" / "price_history.py"
            (root / "src" / "tickertrail").mkdir(parents=True)
            (root / "pyproject.toml").write_text("[project]\nname='tickertrail'\n", encoding="utf-8")
            cwd.mkdir(parents=True)
            module_file.write_text("# stub\n", encoding="utf-8")

            resolved = price_history._resolve_cache_dir(module_file=module_file, cwd=cwd)
            self.assertEqual(resolved, (root / ".cache" / "history").resolve())

    def test_close_points_cache_hits_same_day(self) -> None:
        """Second same-day history request should reuse cache and skip downloader."""
        calls: list[str] = []

        def fake_download(*_args, **_kwargs):
            calls.append("download")
            return _sample_df()

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            old_dir = price_history._CACHE_DIR
            old_day = price_history._CACHE_DAY
            old_store = price_history._CACHE_STORE
            old_metrics = dict(price_history._CACHE_METRICS)
            try:
                price_history._CACHE_DIR = Path(td)
                price_history._CACHE_DAY = None
                price_history._CACHE_STORE = None
                price_history.reset_cache_metrics()

                with patch("tickertrail.price_history._cache_day", return_value="2026-02-22"):
                    p1, c1 = price_history.fetch_close_points_for_token(
                        symbol="RELIANCE.NS",
                        period_token="1y",
                        interval="1d",
                        download_fn=fake_download,
                        track_network_call=lambda _name: None,
                    )
                    p2, c2 = price_history.fetch_close_points_for_token(
                        symbol="RELIANCE.NS",
                        period_token="1y",
                        interval="1d",
                        download_fn=fake_download,
                        track_network_call=lambda _name: None,
                    )
                self.assertEqual(len(calls), 1)
                self.assertEqual(c1, c2)
                self.assertEqual(len(p1), len(p2))
                metrics = price_history.cache_metrics_snapshot()
                self.assertEqual(metrics["hits"], 1)
                self.assertEqual(metrics["misses"], 1)
            finally:
                price_history._CACHE_DIR = old_dir
                price_history._CACHE_DAY = old_day
                price_history._CACHE_STORE = old_store
                price_history._CACHE_METRICS = old_metrics

    def test_close_points_cache_rolls_over_on_new_day(self) -> None:
        """Daily cache should miss on a new day and fetch fresh history."""
        calls: list[str] = []

        def fake_download(*_args, **_kwargs):
            calls.append("download")
            return _sample_df()

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            old_dir = price_history._CACHE_DIR
            old_day = price_history._CACHE_DAY
            old_store = price_history._CACHE_STORE
            try:
                price_history._CACHE_DIR = Path(td)
                price_history._CACHE_DAY = None
                price_history._CACHE_STORE = None

                with patch("tickertrail.price_history._cache_day", return_value="2026-02-22"):
                    price_history.fetch_close_points_for_token(
                        symbol="INFY.NS",
                        period_token="1y",
                        interval="1d",
                        download_fn=fake_download,
                        track_network_call=lambda _name: None,
                    )

                with patch("tickertrail.price_history._cache_day", return_value="2026-02-23"):
                    price_history.fetch_close_points_for_token(
                        symbol="INFY.NS",
                        period_token="1y",
                        interval="1d",
                        download_fn=fake_download,
                        track_network_call=lambda _name: None,
                    )

                self.assertEqual(len(calls), 2)
            finally:
                price_history._CACHE_DIR = old_dir
                price_history._CACHE_DAY = old_day
                price_history._CACHE_STORE = old_store

    def test_clear_history_cache_today_deletes_todays_file(self) -> None:
        """Manual clear should remove today's cache file and reset memory store."""
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            old_dir = price_history._CACHE_DIR
            old_day = price_history._CACHE_DAY
            old_store = price_history._CACHE_STORE
            try:
                price_history._CACHE_DIR = Path(td)
                price_history._CACHE_DAY = None
                price_history._CACHE_STORE = None

                with patch("tickertrail.price_history._cache_day", return_value="2026-02-22"):
                    price_history.fetch_daily_ohlcv_for_period(
                        symbol="TCS.NS",
                        period_token="1y",
                        download_fn=lambda *_args, **_kwargs: _sample_df(),
                        track_network_call=lambda _name: None,
                    )
                    path = Path(td) / "2026-02-22.json"
                    self.assertTrue(path.exists())
                    deleted = price_history.clear_history_cache_today()
                    self.assertTrue(deleted)
                    self.assertFalse(path.exists())
                    self.assertEqual(price_history._CACHE_STORE, {})
            finally:
                price_history._CACHE_DIR = old_dir
                price_history._CACHE_DAY = old_day
                price_history._CACHE_STORE = old_store

    def test_reset_cache_metrics_clears_hit_and_miss_counts(self) -> None:
        """Reset should clear per-command cache counters."""
        price_history._CACHE_METRICS["hits"] = 3
        price_history._CACHE_METRICS["misses"] = 4
        price_history.reset_cache_metrics()
        self.assertEqual(price_history.cache_metrics_snapshot(), {"hits": 0, "misses": 0})

    def test_history_cache_summary_today_reports_kind_symbol_period_interval_counts(self) -> None:
        """Cache summary should expose parsed dimensions for today's in-memory cache keys."""
        old_dir = price_history._CACHE_DIR
        old_day = price_history._CACHE_DAY
        old_store = price_history._CACHE_STORE
        try:
            price_history._CACHE_DIR = Path("/tmp")
            price_history._CACHE_DAY = "2026-03-01"
            price_history._CACHE_STORE = {
                "close_points|INFY.NS|1mo|1d": {"points": [], "prices": []},
                "close_points|TCS.NS|1y|1wk": {"points": [], "prices": []},
                "daily_ohlcv|INFY.NS|1y|1d": {"points": [], "close": [], "high": [], "low": [], "volume": []},
                "bad-key": {},
            }
            with patch("tickertrail.price_history._cache_day", return_value="2026-03-01"):
                summary = price_history.history_cache_summary_today()
            self.assertEqual(summary["day"], "2026-03-01")
            self.assertEqual(summary["entries_total"], 4)
            self.assertEqual(summary["entries_parsed"], 3)
            self.assertEqual(summary["kinds"], {"close_points": 2, "daily_ohlcv": 1})
            self.assertEqual(summary["symbols"], ["INFY.NS", "TCS.NS"])
            self.assertEqual(summary["periods"], ["1mo", "1y"])
            self.assertEqual(summary["intervals"], ["1d", "1wk"])
        finally:
            price_history._CACHE_DIR = old_dir
            price_history._CACHE_DAY = old_day
            price_history._CACHE_STORE = old_store


if __name__ == "__main__":
    unittest.main()
