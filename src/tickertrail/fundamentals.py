from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Callable
from zoneinfo import ZoneInfo

from . import upstox_service


@dataclass(frozen=True)
class HistoryPoint:
    """Hold one reported financial value and its period-over-period move."""

    period: str
    value: float | None
    change_pct: float | None


@dataclass(frozen=True)
class Ratio:
    """Hold one company ratio beside its Upstox sector benchmark."""

    name: str
    company_value: float | None
    sector_value: float | None


@dataclass(frozen=True)
class DividendEvent:
    """Describe one dividend corporate action returned by Upstox."""

    ex_date: dt.date | None
    dividend_type: str
    amount_per_share: float | None


@dataclass(frozen=True)
class CompanyFundamentals:
    """Collect normalized company fundamentals for one terminal dashboard."""

    symbol: str
    display_name: str
    isin: str
    price: float | None
    ratios: tuple[Ratio, ...]
    quarterly: dict[str, tuple[HistoryPoint, ...]]
    annual: dict[str, tuple[HistoryPoint, ...]]
    annual_eps: tuple[HistoryPoint, ...]
    annual_cfo: tuple[HistoryPoint, ...]
    shareholdings: dict[str, tuple[HistoryPoint, ...]]
    dividends: tuple[DividendEvent, ...]
    as_of: dt.date


JsonRequest = Callable[[str, dict[str, str], str], dict[str, Any]]
StyleText = Callable[[str, str | None, bool], str]


def _float_or_none(value: Any) -> float | None:
    """Convert an API scalar to float while tolerating missing or malformed data."""
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _percent_or_none(value: Any) -> float | None:
    """Parse an optional signed percentage string into a numeric percentage."""
    if isinstance(value, str):
        value = value.strip().removesuffix("%")
    return _float_or_none(value)


def _history_points(value: Any) -> tuple[HistoryPoint, ...]:
    """Normalize one Upstox history array without inventing missing values."""
    if not isinstance(value, list):
        return ()
    points: list[HistoryPoint] = []
    for raw_point in value:
        if not isinstance(raw_point, dict):
            continue
        period = str(raw_point.get("period") or "").strip()
        if not period:
            continue
        points.append(
            HistoryPoint(
                period=period,
                value=_float_or_none(raw_point.get("value")),
                change_pct=_percent_or_none(raw_point.get("change")),
            )
        )
    return tuple(points)


def _category_histories(value: Any, category_key: str) -> dict[str, tuple[HistoryPoint, ...]]:
    """Index API category rows by normalized category name."""
    if not isinstance(value, list):
        return {}
    histories: dict[str, tuple[HistoryPoint, ...]] = {}
    for raw_row in value:
        if not isinstance(raw_row, dict):
            continue
        category = str(raw_row.get(category_key) or "").strip().lower()
        if category:
            histories[category] = _history_points(raw_row.get("history"))
    return histories


def _statement_history(value: Any, particular: str) -> tuple[HistoryPoint, ...]:
    """Find one exact line item in an Upstox full financial statement."""
    if not isinstance(value, list):
        return ()
    wanted = particular.casefold()
    for raw_row in value:
        if not isinstance(raw_row, dict):
            continue
        if str(raw_row.get("particular") or "").strip().casefold() == wanted:
            return _history_points(raw_row.get("history"))
    return ()


def _ratios(value: Any) -> tuple[Ratio, ...]:
    """Normalize current company and sector ratio rows."""
    if not isinstance(value, list):
        return ()
    rows: list[Ratio] = []
    for raw_row in value:
        if not isinstance(raw_row, dict):
            continue
        name = str(raw_row.get("name") or "").strip()
        if not name:
            continue
        rows.append(
            Ratio(
                name=name,
                company_value=_percent_or_none(raw_row.get("company_value")),
                sector_value=_percent_or_none(raw_row.get("sector_value")),
            )
        )
    return tuple(rows)


def _api_date(value: Any) -> dt.date | None:
    """Parse an Upstox corporate-action date in its documented display format."""
    try:
        return dt.datetime.strptime(str(value or "").strip(), "%d %b %Y").date()
    except ValueError:
        return None


def _dividend_events(value: Any) -> tuple[DividendEvent, ...]:
    """Normalize dividend actions while ignoring bonus, split, and rights rows."""
    if not isinstance(value, list):
        return ()
    events: list[DividendEvent] = []
    for raw_event in value:
        if not isinstance(raw_event, dict) or str(raw_event.get("name") or "").casefold() != "dividend":
            continue
        detail_rows = raw_event.get("event_details")
        details = {
            str(item.get("name") or "").strip().casefold(): str(item.get("value") or "").strip()
            for item in detail_rows if isinstance(item, dict)
        } if isinstance(detail_rows, list) else {}
        events.append(
            DividendEvent(
                ex_date=_api_date(raw_event.get("expiry_date")),
                dividend_type=details.get("dividend type") or "n/a",
                amount_per_share=_float_or_none(raw_event.get("amount")),
            )
        )
    return tuple(sorted(events, key=lambda event: event.ex_date or dt.date.min, reverse=True))


def fetch_company_fundamentals(
    token: str,
    query: str,
    *,
    preferred_exchange: str = "NSE",
    request_json_fn: JsonRequest | None = None,
    as_of: dt.date | None = None,
) -> CompanyFundamentals:
    """Fetch and normalize one listed company's consolidated Upstox fundamentals."""
    fetch = request_json_fn or upstox_service.request_json
    instrument = upstox_service.resolve_option_underlying(
        token,
        query,
        request_json_fn=fetch,
        preferred_exchange=preferred_exchange,
    )
    if not instrument.segment.endswith("_EQ"):
        raise upstox_service.UpstoxError(
            "Company fundamentals are available only for an active listed stock."
        )
    isin = instrument.instrument_key.partition("|")[2].strip()
    if not isin:
        raise upstox_service.UpstoxError(
            f"Upstox returned no ISIN for {instrument.display_name}."
        )

    # These endpoints are intentionally fixed: the command has no qualifiers and defaults to consolidated data.
    base = f"/v2/fundamentals/{isin}"
    ratio_data = fetch(f"{base}/key-ratios", {}, token).get("data")
    quarterly_data = fetch(
        f"{base}/income-statement",
        {"type": "consolidated", "time_period": "quarterly"},
        token,
    ).get("data")
    annual_data = fetch(
        f"{base}/income-statement",
        {"type": "consolidated", "time_period": "yearly", "fs": "true"},
        token,
    ).get("data")
    cash_data = fetch(
        f"{base}/cash-flow",
        {"type": "consolidated"},
        token,
    ).get("data")
    holding_data = fetch(f"{base}/share-holdings", {}, token).get("data")
    action_data = fetch(f"{base}/corporate-actions", {}, token).get("data")

    quarterly_payload = quarterly_data if isinstance(quarterly_data, dict) else {}
    annual_payload = annual_data if isinstance(annual_data, dict) else {}
    cash_payload = cash_data if isinstance(cash_data, dict) else {}
    quote: upstox_service.UnderlyingQuote | None = None
    try:
        quote = upstox_service.fetch_underlying_quote(
            token,
            instrument.instrument_key,
            instrument.display_name,
            request_json_fn=fetch,
        )
    except upstox_service.UpstoxError:
        # Fundamentals remain useful when the optional current-price request is unavailable.
        quote = None

    annual_full = annual_payload.get("full_statement")
    annual_eps = _statement_history(annual_full, "EPS - Diluted")
    if not annual_eps:
        annual_eps = _statement_history(annual_full, "EPS - Basic")
    cash_histories = _category_histories(cash_payload.get("cash_flow"), "category")
    annual_cfo = cash_histories.get("operating", ())
    if not annual_cfo:
        annual_cfo = _statement_history(
            cash_payload.get("full_statement"), "Cash flow from Operations"
        )
    return CompanyFundamentals(
        symbol=instrument.trading_symbol,
        display_name=instrument.display_name,
        isin=isin,
        price=quote.last_price if quote is not None else None,
        ratios=_ratios(ratio_data),
        quarterly=_category_histories(quarterly_payload.get("income_statement"), "category"),
        annual=_category_histories(annual_payload.get("income_statement"), "category"),
        annual_eps=annual_eps,
        annual_cfo=annual_cfo,
        shareholdings=_category_histories(holding_data, "category"),
        dividends=_dividend_events(action_data),
        as_of=as_of or dt.datetime.now(ZoneInfo("Asia/Kolkata")).date(),
    )


def ratio_value(snapshot: CompanyFundamentals, name: str) -> tuple[float | None, float | None]:
    """Return one case-insensitive company/sector ratio pair."""
    wanted = name.casefold()
    for ratio in snapshot.ratios:
        if ratio.name.casefold() == wanted:
            return ratio.company_value, ratio.sector_value
    return None, None


def peg_ratio(snapshot: CompanyFundamentals) -> float | None:
    """Derive PEG from P/E and the latest three-year diluted-EPS CAGR."""
    pe, _sector = ratio_value(snapshot, "P/E")
    points = [point for point in snapshot.annual_eps if point.value is not None][:4]
    if pe is None or pe <= 0 or len(points) < 4:
        return None
    newest = points[0].value
    oldest = points[3].value
    if newest is None or oldest is None or newest <= 0 or oldest <= 0:
        return None
    growth_pct = ((newest / oldest) ** (1 / 3) - 1) * 100
    return None if growth_pct <= 0 else pe / growth_pct


def book_value_per_share(snapshot: CompanyFundamentals) -> float | None:
    """Derive current book value per share from price divided by P/B."""
    price_to_book, _sector = ratio_value(snapshot, "P/B")
    if snapshot.price is None or price_to_book is None or price_to_book <= 0:
        return None
    return snapshot.price / price_to_book


def trailing_dividend_yield(snapshot: CompanyFundamentals) -> float | None:
    """Derive trailing-12-month dividend yield from returned cash dividends."""
    if snapshot.price is None or snapshot.price <= 0:
        return None
    start = snapshot.as_of - dt.timedelta(days=365)
    total = sum(
        event.amount_per_share or 0.0
        for event in snapshot.dividends
        if event.ex_date is not None and start < event.ex_date <= snapshot.as_of
    )
    return (total / snapshot.price) * 100


def _format_number(value: float | None, decimals: int = 2) -> str:
    """Format an optional number with grouping and a fixed precision."""
    return "n/a" if value is None else f"{value:,.{decimals}f}"


def _format_metric(value: float | None, kind: str) -> str:
    """Format a dashboard metric according to its financial unit."""
    if value is None:
        return "n/a"
    if kind == "percent":
        return f"{value:,.2f}%"
    if kind == "rupees":
        return f"₹{value:,.2f}"
    if kind == "crore":
        return f"₹{value:,.0f} cr"
    return f"{value:,.2f}"


def _periods(*histories: tuple[HistoryPoint, ...]) -> list[str]:
    """Build one stable newest-first union of API history periods."""
    return list(dict.fromkeys(point.period for history in histories for point in history))


def _point_map(history: tuple[HistoryPoint, ...]) -> dict[str, HistoryPoint]:
    """Index one history sequence by reporting period."""
    return {point.period: point for point in history}


def _short_period(period: str, *, annual: bool) -> str:
    """Compact an Upstox month-year label for a terminal table header."""
    try:
        parsed = dt.datetime.strptime(period, "%b %Y")
    except ValueError:
        return period
    return f"FY{parsed.year % 100:02d}" if annual else parsed.strftime("%b '%y")


def _change_color(value: float | None) -> str | None:
    """Map a financial change to positive, negative, or neutral terminal color."""
    if value is None:
        return None
    if value > 0:
        return "green"
    if value < 0:
        return "red"
    return "gray"


def _print_table(
    title: str,
    headers: list[str],
    rows: list[list[str]],
    style_text: StyleText,
    *,
    colors: dict[tuple[int, int], str] | None = None,
) -> None:
    """Render one compact Unicode table with bold headers and optional cell colors."""
    print(f"\n{style_text(title, None, True)}")
    if not rows:
        print("No data returned by Upstox.")
        return
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]

    def border(left: str, middle: str, right: str) -> str:
        """Build one table border from the calculated visible column widths."""
        return left + middle.join("─" * (width + 2) for width in widths) + right

    print(border("┌", "┬", "┐"))
    header_cells = [
        style_text(f" {header:<{widths[index]}} ", None, True)
        for index, header in enumerate(headers)
    ]
    print("│" + "│".join(header_cells) + "│")
    print(border("├", "┼", "┤"))
    for row_index, row in enumerate(rows):
        cells: list[str] = []
        for column_index, value in enumerate(row):
            alignment = "<" if column_index == 0 else ">"
            padded = f" {value:{alignment}{widths[column_index]}} "
            color = (colors or {}).get((row_index, column_index))
            cells.append(style_text(padded, color, False))
        print("│" + "│".join(cells) + "│")
    print(border("└", "┴", "┘"))


def _history_rows(
    periods: list[str],
    series: list[tuple[str, tuple[HistoryPoint, ...], bool]],
) -> tuple[list[list[str]], dict[tuple[int, int], str]]:
    """Build aligned value/change rows and their semantic change colors."""
    rows: list[list[str]] = []
    colors: dict[tuple[int, int], str] = {}
    for label, history, show_change in series:
        by_period = _point_map(history)
        if show_change:
            values = [
                "n/a" if by_period.get(period) is None or by_period[period].change_pct is None
                else f"{by_period[period].change_pct:+.2f}%"
                for period in periods
            ]
            for column_index, period in enumerate(periods, start=1):
                point = by_period.get(period)
                color = _change_color(point.change_pct if point is not None else None)
                if color is not None:
                    colors[(len(rows), column_index)] = color
        else:
            values = [
                _format_number(by_period[period].value, 0) if period in by_period else "n/a"
                for period in periods
            ]
        rows.append([label, *values])
    return rows, colors


def render_company_fundamentals(
    snapshot: CompanyFundamentals,
    style_text: StyleText,
    *,
    updated_at: dt.datetime | None = None,
) -> None:
    """Render a complete consolidated fundamentals dashboard to stdout."""
    now = updated_at or dt.datetime.now(ZoneInfo("Asia/Kolkata"))
    print()
    print(style_text(f"{snapshot.display_name.upper()} · FUNDAMENTALS", None, True))
    print(
        "Consolidated · ₹ crore except per-share values · "
        f"Updated {now.strftime('%d-%m-%Y %H:%M:%S IST')} · Upstox"
    )

    pe, pe_sector = ratio_value(snapshot, "P/E")
    pb, pb_sector = ratio_value(snapshot, "P/B")
    roe, roe_sector = ratio_value(snapshot, "ROE")
    roce, roce_sector = ratio_value(snapshot, "ROCE")
    latest_cfo = next((point.value for point in snapshot.annual_cfo if point.value is not None), None)
    metric_rows = [
        ["P/E", _format_metric(pe, "number"), _format_metric(pe_sector, "number")],
        ["PEG (3Y EPS)*", _format_metric(peg_ratio(snapshot), "number"), "—"],
        ["P/B", _format_metric(pb, "number"), _format_metric(pb_sector, "number")],
        ["Book value/share*", _format_metric(book_value_per_share(snapshot), "rupees"), "—"],
        ["ROE", _format_metric(roe, "percent"), _format_metric(roe_sector, "percent")],
        ["ROCE", _format_metric(roce, "percent"), _format_metric(roce_sector, "percent")],
        ["CFO", _format_metric(latest_cfo, "crore"), "—"],
        ["Dividend yield TTM*", _format_metric(trailing_dividend_yield(snapshot), "percent"), "—"],
    ]
    _print_table("VALUATION & QUALITY", ["Metric", "Company", "Sector"], metric_rows, style_text)

    revenue = snapshot.quarterly.get("revenue", ())
    quarterly_pat = snapshot.quarterly.get("net_profit", ())
    quarter_periods = _periods(revenue, quarterly_pat)
    quarter_rows, quarter_colors = _history_rows(
        quarter_periods,
        [
            ("Sales", revenue, False),
            ("Sales QoQ", revenue, True),
            ("PAT", quarterly_pat, False),
            ("PAT QoQ", quarterly_pat, True),
        ],
    ) if quarter_periods else ([], {})
    _print_table(
        "QUARTERLY PERFORMANCE",
        ["₹ crore", *[_short_period(period, annual=False) for period in quarter_periods]],
        quarter_rows,
        style_text,
        colors=quarter_colors,
    )

    annual_pat = snapshot.annual.get("net_profit", ())
    annual_periods = _periods(annual_pat, snapshot.annual_cfo)
    annual_rows, annual_colors = _history_rows(
        annual_periods,
        [
            ("PAT", annual_pat, False),
            ("PAT YoY", annual_pat, True),
            ("CFO", snapshot.annual_cfo, False),
            ("CFO YoY", snapshot.annual_cfo, True),
        ],
    ) if annual_periods else ([], {})
    _print_table(
        "ANNUAL PROFIT & CASH FLOW",
        ["₹ crore", *[_short_period(period, annual=True) for period in annual_periods]],
        annual_rows,
        style_text,
        colors=annual_colors,
    )

    holding_order = ("promoters", "fii", "mutual_funds", "other_dii", "retail_and_other")
    holding_labels = {
        "promoters": "Promoters",
        "fii": "FII",
        "mutual_funds": "Mutual funds",
        "other_dii": "Other DII",
        "retail_and_other": "Retail & others",
    }
    holding_periods = _periods(*(snapshot.shareholdings.get(key, ()) for key in holding_order))
    holding_rows = []
    for key in holding_order:
        by_period = _point_map(snapshot.shareholdings.get(key, ()))
        holding_rows.append(
            [
                holding_labels[key],
                *[
                    _format_metric(by_period[period].value, "percent") if period in by_period else "n/a"
                    for period in holding_periods
                ],
            ]
        )
    _print_table(
        "SHAREHOLDING",
        ["Holder", *[_short_period(period, annual=False) for period in holding_periods]],
        holding_rows if holding_periods else [],
        style_text,
    )

    dividend_rows = [
        [
            event.ex_date.strftime("%d %b %Y") if event.ex_date is not None else "n/a",
            event.dividend_type,
            _format_metric(event.amount_per_share, "rupees"),
        ]
        for event in snapshot.dividends
    ]
    _print_table(
        "DIVIDEND HISTORY",
        ["Ex-date", "Type", "Dividend/share"],
        dividend_rows,
        style_text,
    )

    print(
        "\n* Derived by TickerTrail: PEG uses 3Y diluted-EPS CAGR; "
        "book value/share uses price ÷ P/B; dividend yield uses returned TTM dividends ÷ price."
    )
    print(
        "History returned by Upstox: "
        f"{len(quarter_periods)} quarters · {len(annual_periods)} years · "
        f"{len(holding_periods)} shareholding quarters · {len(snapshot.dividends)} dividend events."
    )
