from __future__ import annotations

import datetime as dt
import io
import unittest
from unittest.mock import patch

from tickertrail import fundamentals
from tickertrail import upstox_service


def _history(*values: tuple[str, float, str]) -> list[dict[str, object]]:
    """Build one deterministic Upstox financial history array."""
    return [
        {"period": period, "value": value, "change": change}
        for period, value, change in values
    ]


def _payload_for(endpoint: str) -> dict[str, object]:
    """Return a complete mocked Upstox response for one fundamentals endpoint."""
    if endpoint == "/v2/instruments/search":
        return {
            "data": [
                {
                    "name": "RELIANCE INDUSTRIES LTD",
                    "short_name": "Reliance",
                    "trading_symbol": "RELIANCE",
                    "instrument_key": "NSE_EQ|INE002A01018",
                    "segment": "NSE_EQ",
                    "exchange": "NSE",
                }
            ]
        }
    if endpoint.endswith("/key-ratios"):
        return {
            "data": [
                {"name": "P/E", "company_value": "24", "sector_value": "20"},
                {"name": "P/B", "company_value": "2", "sector_value": "1.8"},
                {"name": "ROE", "company_value": "12.5%", "sector_value": "11.2%"},
                {"name": "ROCE", "company_value": "14.5%", "sector_value": "13.2%"},
                {"name": "bad", "company_value": "nope", "sector_value": None},
                "malformed",
            ]
        }
    if endpoint.endswith("/income-statement"):
        return {}
    if endpoint.endswith("/cash-flow"):
        return {
            "data": {
                "cash_flow": [
                    {
                        "category": "operating",
                        "history": _history(
                            ("Mar 2026", 1000, "+10%"),
                            ("Mar 2025", 900, "-5%"),
                            ("Mar 2024", 950, "+3%"),
                            ("Mar 2023", 920, "+2%"),
                        ),
                    }
                ],
                "full_statement": [],
            }
        }
    if endpoint.endswith("/share-holdings"):
        history = _history(
            ("Jun 2026", 50.1, "+0.1%"),
            ("Mar 2026", 50.0, "0%"),
            ("Dec 2025", 49.9, "-0.1%"),
            ("Sep 2025", 50.0, "+0.1%"),
        )
        return {
            "data": [
                {"category": category, "history": history}
                for category in (
                    "promoters",
                    "fii",
                    "other_dii",
                    "retail_and_other",
                    "mutual_funds",
                )
            ]
        }
    if endpoint.endswith("/corporate-actions"):
        return {
            "data": [
                {
                    "name": "Dividend",
                    "expiry_date": "05 Jun 2026",
                    "amount": 6,
                    "event_details": [{"name": "Dividend type", "value": "Final"}],
                },
                {
                    "name": "Dividend",
                    "expiry_date": "14 Aug 2025",
                    "amount": 5.5,
                    "event_details": [{"name": "Dividend type", "value": "Final"}],
                },
                {"name": "Split", "expiry_date": "bad", "ratio": "2:1"},
            ]
        }
    if endpoint == "/v3/market-quote/ltp":
        return {"data": {"NSE_EQ:RELIANCE": {"last_price": 1000, "cp": 990}}}
    raise AssertionError(endpoint)


def _fake_request(endpoint, params, token):
    """Serve deterministic responses while preserving the request signature."""
    if endpoint.endswith("/income-statement"):
        if params.get("time_period") == "quarterly":
            periods = (
                ("Jun 2026", 250, "+4%"),
                ("Mar 2026", 240, "-2%"),
                ("Dec 2025", 245, "+3%"),
                ("Sep 2025", 238, "+1%"),
            )
            return {
                "data": {
                    "income_statement": [
                        {"category": "revenue", "history": _history(*periods)},
                        {
                            "category": "net_profit",
                            "history": _history(
                                ("Jun 2026", 25, "+5%"),
                                ("Mar 2026", 24, "-3%"),
                                ("Dec 2025", 24.8, "+2%"),
                                ("Sep 2025", 24.3, "+1%"),
                            ),
                        },
                    ]
                }
            }
        annual = _history(
            ("Mar 2026", 160, "+10%"),
            ("Mar 2025", 128, "+8%"),
            ("Mar 2024", 102.4, "+5%"),
            ("Mar 2023", 80, "+4%"),
        )
        return {
            "data": {
                "income_statement": [{"category": "net_profit", "history": annual}],
                "full_statement": [{"particular": "EPS - Diluted", "history": annual}],
            }
        }
    return _payload_for(endpoint)


class FundamentalsTests(unittest.TestCase):
    def test_fetch_normalizes_all_dashboard_sources_and_request_parameters(self):
        """Fetch every fixed endpoint and preserve four returned reporting periods."""
        calls: list[tuple[str, dict[str, str], str]] = []

        def recording_request(endpoint, params, token):
            """Record calls before serving the deterministic fixture."""
            calls.append((endpoint, params, token))
            return _fake_request(endpoint, params, token)

        snapshot = fundamentals.fetch_company_fundamentals(
            "token",
            "RELIANCE",
            request_json_fn=recording_request,
            as_of=dt.date(2026, 8, 14),
        )

        self.assertEqual(snapshot.isin, "INE002A01018")
        self.assertEqual(snapshot.price, 1000)
        self.assertEqual(len(snapshot.quarterly["revenue"]), 4)
        self.assertEqual(len(snapshot.annual["net_profit"]), 4)
        self.assertEqual(len(snapshot.annual_cfo), 4)
        self.assertEqual(fundamentals.ratio_value(snapshot, "ROE"), (12.5, 11.2))
        self.assertEqual(len(snapshot.shareholdings["promoters"]), 4)
        self.assertEqual(len(snapshot.dividends), 2)
        self.assertEqual(len(calls), 8)
        annual_call = next(
            call for call in calls
            if call[0].endswith("income-statement") and call[1].get("time_period") == "yearly"
        )
        self.assertEqual(
            annual_call[1],
            {"type": "consolidated", "time_period": "yearly", "fs": "true"},
        )
        self.assertTrue(all(call[2] == "token" for call in calls))

    def test_derived_metrics_use_three_year_eps_and_trailing_dividends(self):
        """Calculate PEG, book value/share, and TTM yield from explicit inputs."""
        snapshot = fundamentals.fetch_company_fundamentals(
            "token", "RELIANCE", request_json_fn=_fake_request, as_of=dt.date(2026, 8, 14)
        )
        pe, sector = fundamentals.ratio_value(snapshot, "p/e")
        self.assertEqual((pe, sector), (24, 20))
        self.assertAlmostEqual(fundamentals.peg_ratio(snapshot) or 0, 24 / 25.9921, places=3)
        self.assertEqual(fundamentals.book_value_per_share(snapshot), 500)
        self.assertAlmostEqual(fundamentals.trailing_dividend_yield(snapshot) or 0, 0.6)
        self.assertEqual(fundamentals.ratio_value(snapshot, "missing"), (None, None))

    def test_renderer_outputs_requested_sections_and_cfo_not_fcf(self):
        """Render the approved four-period dashboard with derivation disclosure."""
        snapshot = fundamentals.fetch_company_fundamentals(
            "token", "RELIANCE", request_json_fn=_fake_request, as_of=dt.date(2026, 8, 14)
        )

        def style(text: str, color: str | None = None, bold: bool = False) -> str:
            """Expose semantic styles as deterministic test markers."""
            prefix = f"<{color or 'plain'}{'-bold' if bold else ''}>"
            return f"{prefix}{text}</>"

        with patch("sys.stdout", new_callable=io.StringIO) as out:
            fundamentals.render_company_fundamentals(
                snapshot,
                style,
                updated_at=dt.datetime(2026, 8, 14, 12, 30),
            )
        text = out.getvalue()
        self.assertIn("RELIANCE · FUNDAMENTALS", text)
        self.assertIn("VALUATION & QUALITY", text)
        self.assertIn("QUARTERLY PERFORMANCE", text)
        self.assertIn("ANNUAL PROFIT & CASH FLOW", text)
        self.assertIn("SHAREHOLDING", text)
        self.assertIn("DIVIDEND HISTORY", text)
        self.assertIn("CFO", text)
        self.assertNotIn("FCF", text)
        self.assertIn("Jun '26", text)
        self.assertIn("FY26", text)
        self.assertIn("4 quarters · 4 years · 4 shareholding quarters · 2 dividend events", text)
        self.assertIn("<green>", text)
        self.assertIn("<red>", text)
        self.assertIn("<plain-bold>", text)

    def test_missing_and_malformed_inputs_render_as_unavailable(self):
        """Keep sparse company responses readable without false derived values."""
        snapshot = fundamentals.CompanyFundamentals(
            symbol="BANK",
            display_name="BANK",
            isin="INE000000001",
            price=None,
            ratios=(fundamentals.Ratio("P/E", 10, None),),
            quarterly={},
            annual={},
            annual_eps=(
                fundamentals.HistoryPoint("Mar 2026", -2, None),
                fundamentals.HistoryPoint("Mar 2025", 1, None),
                fundamentals.HistoryPoint("Mar 2024", 1, None),
                fundamentals.HistoryPoint("Mar 2023", 1, None),
            ),
            annual_cfo=(),
            shareholdings={},
            dividends=(fundamentals.DividendEvent(None, "n/a", None),),
            as_of=dt.date(2026, 8, 14),
        )
        self.assertIsNone(fundamentals.peg_ratio(snapshot))
        self.assertIsNone(fundamentals.book_value_per_share(snapshot))
        self.assertIsNone(fundamentals.trailing_dividend_yield(snapshot))
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            fundamentals.render_company_fundamentals(
                snapshot,
                lambda text, _color=None, _bold=False: text,
                updated_at=dt.datetime(2026, 8, 14),
            )
        self.assertGreaterEqual(out.getvalue().count("No data returned by Upstox."), 3)
        self.assertIn("n/a", out.getvalue())

    def test_sparse_normalizers_and_statement_fallbacks(self):
        """Cover malformed collections plus basic-EPS and detailed-CFO fallbacks."""
        self.assertEqual(fundamentals._history_points(None), ())
        self.assertEqual(fundamentals._history_points(["bad", {}, {"period": ""}]), ())
        self.assertEqual(fundamentals._category_histories(None, "category"), {})
        self.assertEqual(fundamentals._category_histories(["bad"], "category"), {})
        self.assertEqual(fundamentals._statement_history(None, "PAT"), ())
        self.assertEqual(fundamentals._statement_history(["bad", {"particular": "Tax"}], "PAT"), ())
        self.assertEqual(fundamentals._ratios(None), ())
        self.assertEqual(fundamentals._ratios([{"name": ""}]), ())
        self.assertIsNone(fundamentals._api_date("not-a-date"))
        self.assertEqual(fundamentals._dividend_events(None), ())
        self.assertEqual(fundamentals._short_period("unknown", annual=False), "unknown")
        self.assertIsNone(fundamentals._change_color(None))
        self.assertEqual(fundamentals._change_color(0), "gray")

        def fallback_request(endpoint, params, token):
            """Replace only annual EPS and CFO payloads with fallback line items."""
            payload = _fake_request(endpoint, params, token)
            if endpoint.endswith("/income-statement") and params.get("time_period") == "yearly":
                data = payload["data"]
                assert isinstance(data, dict)
                full = data["full_statement"]
                assert isinstance(full, list)
                full[0]["particular"] = "EPS - Basic"
            if endpoint.endswith("/cash-flow"):
                data = payload["data"]
                assert isinstance(data, dict)
                history = data["cash_flow"][0]["history"]
                data["cash_flow"] = []
                data["full_statement"] = [
                    {"particular": "Cash flow from Operations", "history": history}
                ]
            return payload

        snapshot = fundamentals.fetch_company_fundamentals(
            "token", "RELIANCE", request_json_fn=fallback_request
        )
        self.assertEqual(len(snapshot.annual_eps), 4)
        self.assertEqual(len(snapshot.annual_cfo), 4)

    def test_fetch_rejects_indices_and_missing_isin_but_tolerates_quote_failure(self):
        """Enforce company scope while allowing a price-independent dashboard."""
        def index_request(endpoint, _params, _token):
            """Resolve an exact index so the company-only guard can reject it."""
            if endpoint == "/v2/instruments/search":
                return {
                    "data": [{
                        "name": "NIFTY 50",
                        "short_name": "Nifty 50",
                        "trading_symbol": "NIFTY 50",
                        "instrument_key": "NSE_INDEX|Nifty 50",
                        "segment": "NSE_INDEX",
                        "exchange": "NSE",
                    }]
                }
            raise AssertionError(endpoint)

        with self.assertRaisesRegex(upstox_service.UpstoxError, "only for an active listed stock"):
            fundamentals.fetch_company_fundamentals("token", "Nifty 50", request_json_fn=index_request)

        with patch(
            "tickertrail.fundamentals.upstox_service.resolve_option_underlying",
            return_value=upstox_service.OptionUnderlying("NSE_EQ|", "BAD", "BAD", "NSE_EQ"),
        ):
            with self.assertRaisesRegex(upstox_service.UpstoxError, "no ISIN"):
                fundamentals.fetch_company_fundamentals("token", "BAD", request_json_fn=_fake_request)

        def no_quote_request(endpoint, params, token):
            """Fail only the optional quote after serving all fundamental datasets."""
            if endpoint == "/v3/market-quote/ltp":
                raise upstox_service.UpstoxError("quote unavailable")
            return _fake_request(endpoint, params, token)

        snapshot = fundamentals.fetch_company_fundamentals(
            "token", "RELIANCE", request_json_fn=no_quote_request
        )
        self.assertIsNone(snapshot.price)


if __name__ == "__main__":
    unittest.main()
