# Tickertrail Rebuild Playbook (Agent Prompts)

This document is the canonical prompt pack for rebuilding `tickertrail` from scratch with high predictability.

Use these prompts in order. Do not skip phases.

## 0) Product Contract (Freeze This First)
```text
You are rebuilding tickertrail, a terminal-first stock CLI.

Primary user profile:
- India-first equity user who also tracks US/global markets.

Product contract:
- Python CLI app, launched via `uv run tickertrail`.
- If no args, start interactive REPL.
- REPL prompt format:
  - no active symbol: `tt> `
  - stock context: `tt>stock><symbol_token>> `
  - index context: `tt>index><index_token>> `
  - watchlist context: `tt>watchlist><name>> `
  - configuration context: `tt>config> `
  - examples: `tt>stock>infy> `, `tt>index>bank> `, `tt>watchlist>sharekhan> `, `tt>config> `
- Date format in general user output: `dd-mm-yy`; option expiry headings use `dd-Mon-yyyy`.

Core commands:
- `h` / `help [topic|command]`: organized command reference with examples; topic shortcuts include `core`, `chart`, `table`, `watchlist`, `index`, and `help <command>` prints detailed usage/defaults/examples for that command.
- `?`: print a concise, network-free command list for the active prompt stage (`tt`, stock, index, watchlist, or config); watchlist help includes the active watchlist name and only commands applicable from that context.
- `<command-prefix> ?`: intercept any trailing question mark before all execution/parsing paths, resolve complete or nested aliases by longest command prefix, and show grammar filtered to the active stage. An unavailable command reports its required context; an unknown prefix points to bare `?`. This path must make zero symbol, cache, subprocess, or provider calls.
- `quote` / `q`: print quote for current symbol/index context (disallow in watchlist mode).
- `quit` / `exit`: leave REPL.
- `cls`/`clear`: clear terminal screen (must not trigger symbol resolution).
- `!<shell-cmd>`: pass command to underlying shell from REPL.
- `cache`: print today's persisted history-cache summary (path, counts, symbols, dimensions).
- `cache clear`: clear only today's persisted history cache bucket.
- `reload` / `r`: refresh active quote and replay last chart/table view.
- `index`: live market board with India + Global sections.
- `index list`: curated index universe (symbol catalog) without live fetch.
- `config`: enter a single-level configuration mode; `end` or `exit` returns to `tt>`.
- `token add upstox <token>` in configuration mode: save the token inline without an interactive secret prompt.
- `show token` / `show token upstox` from normal prompts: report configured state and file path without displaying the token; do not make status available inside configuration mode.
- `chain` / `oc` in a stock/index context: show its Upstox option chain when it has listed F&O contracts; elsewhere require `chain <symbol|index> ...`.
- `opt` / `option` in a stock/index context: compare CE and PE details for one exactly listed strike; elsewhere require `opt <symbol|index> <strike> ...`.
- `fundmentals` / `funda` in a stock context: show the active listed company's consolidated Upstox fundamentals; accept no target or qualifier arguments and keep it unavailable at root, index, watchlist, and config prompts.
- `Ctrl+C` while a command is running: cancel only the active command, reset transient progress output, and return to the REPL prompt.
- `Ctrl+C` on an idle prompt: exit the REPL.
- `news <code>`: resolve symbol and print latest Yahoo Finance headlines (best-effort availability per ticker/region).
  - Render publish time in local timezone with relative age when available; parse timestamp fields from both top-level items and nested `content` payloads.
  - Keep output compact: `* (age) headline` plus link on next line, one blank line between items, no source row.
  - Keep colors subtle and terminal-safe: cyan headline line + gray link line when ANSI color is available.
  - Accept index aliases as `<code>` so `news` works for common index names (`nifty`, `it`, `metals`, `consumer`, `defence`, `dow`).
- `snap`: constituent price snapshot for supported active board index symbols.
- `watchlist create <name>` / `wl create <name>`: create local watchlist.
- `watchlist list` / `wl list`: list local watchlists.
- `watchlist delete <name>` / `wl delete <name>`: delete local watchlist.
- `watchlist merge <wl1> <wl2> <target>` / `wl merge <wl1> <wl2> <target>`: union two source watchlists into target (create target if missing; preserve stable de-dup order).
- `watchlist open <name>` / `wl open <name>`: enter watchlist mode (prompt becomes `tt>watchlist><name>> `).
- `watchlist <name>` / `wl <name>`: shorthand for `watchlist open <name>`.
- `watchlist`: exit watchlist mode.
- bare `wl`: alias for `wl list`.
- if watchlist DB reads fail transiently, surface a DB read error explicitly; do not misreport the watchlist as missing.
- while in watchlist mode, typing a symbol switches to stock quote mode and exits watchlist mode.
- `add <code...>`: add validated stock codes in active watchlist mode.
  - when a symbol already exists in the active watchlist, print an explicit "already exists" message.
  - validate using bundled local NSE universe data only (no network fetches while adding), merging the main equity CSV with a curated supplemental symbol list for ETF/fund coverage.
- `delete <code...>`: remove symbols from active watchlist mode.
- `delete all`: remove every symbol from the active watchlist in one operation after an explicit `yes` confirmation; report the deleted count and handle empty, missing, and database-error states explicitly.
- `list` in watchlist mode: print symbols in current watchlist.
- `snap` in watchlist mode: show snapshot for symbols in that watchlist.
- `move [Nd|Nmo(<12)|Ny]` in watchlist mode: show move-dot rows for all symbols (`moves` alias supported; default `1mo`).
- `move on <code1> <code2> ... [Nd|Nmo(<12)|Ny]`: explicit symbol override for `move`/`moves`.
- `trend` in watchlist mode: show current trend-score rows for all symbols (`trends` alias supported).
- `trend on <code1> <code2> ...`: explicit symbol override for `trend`/`trends`.
- `relret [Nd|Nmo(<12)|Ny] [vs <benchmark> [Nd|Nmo(<12)|Ny]]` in watchlist mode: show relative-return ranking (alias `rr`; default `1mo`).
- `relret on <code1> <code2> ... [Nd|Nmo(<12)|Ny] [vs <benchmark> [Nd|Nmo(<12)|Ny]]`: explicit symbol override for `relret`.
- `corr [Nd|Nmo(<12)|Ny]` in watchlist mode: show return-correlation summary (default `1mo`).
- `corr on <code1> <code2> ... [Nd|Nmo(<12)|Ny]`: explicit symbol override for `corr`.
  - sort rows as gainers first (largest gain to smallest), then losers (smallest fall to largest), then unknowns.
  - include `Equal-Weight 1D` as average of available constituent daily percent changes.
  - include benchmark diagnostics:
    - `NIFTY 50 1D` from the same grouped snapshot fetch
    - `Alpha` as `Equal-Weight 1D - NIFTY 50 1D`
- `c`: swing chart with benchmark co-plotted on same axis.
- `cc`: intraday-only chart.
- `t`: rebased table only (no chart).
- `tt`: intraday-first rebased table mode (table-only counterpart to `cc`).
- canonical chart/table grammar:
  - `chart swing ...` (alias family: `c ...`)
  - `chart intra ...` (alias family: `cc ...`)
  - `table swing ...` (alias family: `t ...`)
  - `table intra ...` (alias family: `tt ...`)
- `cmp`: multi-instrument rebased compare table (no benchmark alpha/delta columns).
- `code <query>`: show likely ticker codes from local NSE universe fuzzy matching.
- symbol input: switch active symbol + print quote.

Non-negotiable grammar:
- `t`
- `t <benchmark>`
- `t <benchmark> <period>`
- `t - <period|agg> [agg]`
- `t <benchmark> - <period|agg> [agg]`
- same grammar for `c`
- `cc`, `cc <1m|5m|15m|30m|1hr>`, `cc <benchmark>`, `cc <benchmark> <1m|5m|15m|30m|1hr>`
- `cc - <1m|5m|15m|30m|1hr>`, `cc <benchmark> - <1m|5m|15m|30m|1hr>`
- `tt`, `tt <1m|5m|15m|30m|1hr>`, `tt <benchmark>`, `tt <benchmark> <1m|5m|15m|30m|1hr>`
- `tt - <1m|5m|15m|30m|1hr>`, `tt <benchmark> - <1m|5m|15m|30m|1hr>`
- canonical equivalents:
  - `chart swing`, `chart swing <benchmark>`, `chart swing <benchmark> <period>`, `chart swing - <period|agg> [agg]`, `chart swing <benchmark> - <period|agg> [agg]`
  - `chart intra`, `chart intra <1m|5m|15m|30m|1hr>`, `chart intra <benchmark>`, `chart intra <benchmark> <1m|5m|15m|30m|1hr>`
  - `chart intra - <1m|5m|15m|30m|1hr>`, `chart intra <benchmark> - <1m|5m|15m|30m|1hr>`
  - `table swing`, `table swing <benchmark>`, `table swing <benchmark> <period>`, `table swing - <period|agg> [agg]`, `table swing <benchmark> - <period|agg> [agg]`
  - `table intra`, `table intra <1m|5m|15m|30m|1hr>`, `table intra <benchmark>`, `table intra <benchmark> <1m|5m|15m|30m|1hr>`
  - `table intra - <1m|5m|15m|30m|1hr>`, `table intra <benchmark> - <1m|5m|15m|30m|1hr>`
- `cmp <symbol1> <symbol2> [symbolN ...] [period [agg]]`
- `code <company-or-symbol-query>`
- `watchlist create <name>` / `wl create <name>`
- `watchlist list` / `wl list`
- `watchlist delete <name>` / `wl delete <name>`
- `watchlist merge <wl1> <wl2> <target>` / `wl merge <wl1> <wl2> <target>`
- `watchlist open <name>` / `wl open <name>`
- `watchlist <name>` / `wl <name>` (shorthand)
- bare `wl` (aliases to `wl list`)
- `add <symbol1> [symbolN ...]` (watchlist mode)
- `delete <symbol1> [symbolN ...]` (watchlist mode)
- `list` (watchlist mode)
- `config` (enter configuration mode)
- `token add upstox <token>` / `end` (configuration mode)
- `show token` / `show token upstox` (normal root, stock, index, or watchlist prompt)
- `chain <symbol|index> [near|next|far|month] [strikes <1-25>]`
- `chain <symbol|index> expiry YYYY-MM-DD [strikes <1-25>]`
- `chain [near|next|far|month] [strikes <1-25>]` (stock/index context)
- `chain expiry YYYY-MM-DD [strikes <1-25>]` (stock/index context)
- `opt <strike> [near|next|far|month]` (stock/index context)
- `opt <strike> expiry YYYY-MM-DD` (stock/index context)
- `opt <symbol|index> <strike> [near|next|far|month]` (any normal prompt)
- `opt <symbol|index> <strike> expiry YYYY-MM-DD` (any normal prompt)
- `fundmentals` / `funda` (stock context only; no qualifiers)

Usability preference:
- Prefer non-dash forms in docs/examples (`c nifty 3mo w`, `t nifty 2y mo`).
- Keep dash forms as advanced variants for explicit structure-preserving intent.

Token conventions:
- period units: `d`, `w`, `mo`, `y`, and `max`
- aggregation units: `m` (minute), `d`, `w`, `mo`, `y`
- strict meaning:
  - `m` is always minute
  - `mo` is always month

Persistence conventions:
- Store watchlist data in `data/db.json`.
- Store the Upstox analytics token in repository-local `.upstox_analytics_token`, mode `0600`, and ignore it in Git.
- JSON shape:
  - top-level object with `watchlists` map
  - watchlist names as keys and de-duplicated symbol arrays as values
```

## 1) Architecture Prompt
```text
Design a small architecture for tickertrail with clear separation:

1) Input grammar layer
- Keep typed, pure parse functions in `command_parser.py`; retain thin `cli.py` wrappers only where compatibility requires them.
- No network calls.
- Dataclass output.

2) Resolution/data layer
- Symbol resolution and fallback matching.
- Yahoo Finance fetch wrappers.
- Period/interval validation.
- Keep period/aggregation normalization and compatibility policy in a reusable module (for example `timeframe.py`) so non-CLI features can share it without importing REPL/controller code.
- Keep market-session logic in a reusable module (for example `market_hours.py`) and quote trend-dot generation in a reusable module (for example `quote_tools.py`) so chart/quote/screener features can reuse them without importing REPL/controller flow.
- Keep historical close-series retrieval in a reusable module (for example `price_history.py`) with injected downloader/telemetry callbacks so non-CLI workflows can reuse it and tests can stub network cleanly.
- Keep quote/rebased/compare presentation logic in a reusable views module (for example `views.py`) and let `cli.py` call it as an adapter layer.
- Keep grouped snapshot/day-range enrichment logic in a reusable service module (for example `snapshot_service.py`) with injected fetch/progress callbacks so index/snap features are reusable outside REPL.
- Keep Upstox token persistence, exact stock/index instrument search, F&O contract validation, contract-calendar expiry resolution, HTTP normalization, option-chain parsing, exact strike selection, grouped full-quote normalization, and ATM-window selection in `upstox_service.py`; allow injected request callbacks so tests never use the live API.
- Keep Upstox company-fundamentals fetching, normalization, derived metrics, and dashboard rendering in `fundamentals.py`; limit `cli.py` to stock-context dispatch and network telemetry.
- Keep canonical index aliases, board membership, Yahoo fetch mappings, expected constituent counts, and prompt labels in `index_config.py`; `cli.py` may expose compatibility aliases but should not duplicate the configuration.

3) Render layer
- Quote renderer
- Chart renderer (plotext)
- Table renderer
- Index board renderer

4) REPL/controller layer
- command dispatch
- active symbol state
- prompt string generation
- Keep overview/topic/command help definitions, prefix resolution, and stage-applicability policy in a data-driven `repl_help.py` module rather than nested in the REPL loop.
- Keep `cli.py` focused on orchestration; do not reintroduce long presentation catalogs into `_run_repl()`.

Output expected:
- a short architecture map
- module/function boundaries
- explicit list of pure/testable functions
```

## 2) File Skeleton Prompt
```text
Create minimal file layout:

- src/tickertrail/cli.py
- src/tickertrail/command_parser.py
- src/tickertrail/index_config.py
- src/tickertrail/repl_help.py
- src/tickertrail/market_hours.py
- src/tickertrail/price_history.py
- src/tickertrail/quote_tools.py
- src/tickertrail/snapshot_service.py
- src/tickertrail/timeframe.py
- src/tickertrail/upstox_service.py
- src/tickertrail/views.py
- tests/test_cli_parsing.py
- tests/test_cli_commands.py
- tests/test_cli_branches.py
- tests/test_command_parser.py
- tests/test_repl_help.py
- tests/test_upstox_cli.py
- tests/test_upstox_service.py

Conventions:
- docstrings on every function (including nested local helpers).
- concise comments on major decision blocks.
- no dead code.
- no network in parser tests.
```

## 3) Command Grammar Prompt (Parser Agent)
```text
Implement parser dataclasses:
- ParsedSwingCommand(period_token: str='6mo', interval_override: str|None=None, benchmark_input: str|None=None)
- ParsedIntradayCommand(interval: str='5m', benchmark_input: str|None=None)

Implement pure parse functions:
- parse_swing_args(args: list[str], command_name: str) -> (ParsedSwingCommand|None, str|None)
- parse_intraday_args(args: list[str]) -> (ParsedIntradayCommand|None, str|None)

Rules:
- Preserve legacy forms and new dash forms.
- Prefer `<period> <agg>` when both tokens match.
- If 1 token in swing mode:
  - parse as period if valid
  - else treat as benchmark symbol input
- Return human-readable usage errors.

Forbidden:
- network fetches
- side effects
```

## 4) Token Normalization Prompt
```text
Implement token utilities:
- normalize_period_token(str) -> str|None
- period_token_days(str) -> int|None
- normalize_agg_token(str) -> str|None

Expected behavior:
- accepted period: `1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,max` and `N[d|w|mo|y]`
- rejected: `3m` (invalid for period), `0y`, garbage tokens
- accepted agg shortcuts:
  - m -> 1m
  - d -> 1d
  - w -> 1wk
  - mo -> 1mo
  - and explicit yfinance intervals where valid
- default table-bin policy:
  - `<=7d -> 1d`
  - `<=1mo -> 1wk`
  - `>1mo and <=3y -> 1mo`
  - `>3y -> 1y`
```

## 5) Period/Interval Validator Prompt
```text
Implement:
- validate_period_interval(period_token, interval) -> error_message|None

Requirements:
- must run before data fetch in chart/table flows.
- clear failures, e.g.:
  - unsupported period
  - unsupported interval
  - interval retention breaches (intraday limits)

Baseline retention guardrails:
- 1m supports <= 7d
- other intraday intervals support <= 60d
- reject intraday with period=max

Add tests for valid and invalid combinations.
```

## 6) Symbol Resolution Prompt
```text
Implement India-first symbol resolution:
- candidate order for bare symbol: `.NS`, `.BO`, then raw
- handle known index aliases
- Keep index aliases in index-resolution flow even when quote payload is empty; do not fall back to NSE fuzzy equity picker for alias tokens (for example `defence`).
- if unresolved, fallback to local NSE universe fuzzy search
- if one match, auto-pick
- if multiple + TTY, ask user to choose
- if non-TTY, print top candidates and fail cleanly

Key requirement:
- keep this flow robust but predictable; avoid hidden heuristics.
```

## 7) Quote Renderer Prompt
```text
Implement compact quote output:

Header line:
- `<RESOLVED_SYMBOL>  <NAME>  [<CURRENCY>]`

Body lines:
- Px / Chg / Open / Day L-H
- Vol / MCap / Updated timestamp
- Day Range line (ASCII range bar)
- 30D Moves line under Day Range (green/red dots for up/down daily close moves)
  - derive from latest 30 trading-session closes using buffered daily lookback (not strict 30 calendar days)
  - ignore non-finite close values (for example NaN placeholders) before computing per-session direction dots
- 52W Range line (ASCII range bar)
- Returns line under 30D Moves:
  - show `7D`, `1MO`, `3MO`, `6MO`, `9MO`, `1Y` percent returns
  - derive all horizons from one daily close history fetch (reuse series for all horizons)
  - use calendar anchors (7 days / 1 month / 6 months / 1 year) from latest trading date
  - choose baseline close via as-of lookup: last available trading close on or before each anchor
  - render missing horizons as `n/a` when insufficient history exists
- Signal diagnostics block under Returns:
  - `Signal`: `TrendScore` (5 checks), `RSI14`, `Vol/20D`
  - `Risk`: `MaxDD(1Y)`, `WinRate(1Y)`
  - `Extremes`: `Best`, `Worst`, `Skew`
  - compute these from the same shared 1y daily OHLCV payload used for return/dot lines
  - preserve quote performance by avoiding extra history network calls per signal
- Optional fundamentals when available:
  - PE(TTM) else PE(FWD)
  - PEG
  - ROE
  - ROCE
  - FCF

Constraints:
- no "Resolved ..." extra line
- keep tight vertical footprint
- color by sign where meaningful
```

## 8) Chart Renderer Prompt (plotext locked)
```text
Use `plotext` only.

Global chart config:
- theme: pro
- plotsize: width=100, height=22 default
- frame=True, grid on Y only, yfrequency=8
- xlabel='Date', ylabel='Price'
- title format: "{SYMBOL} close ({period}, {interval})  {move}"

Series styling:
- stock line:
  - green if end>=start else red
  - marker='hd'
  - last point marker cyan
- benchmark co-plot:
  - rebase benchmark to stock start value
  - yellow line, white final marker
- discard non-finite close rows and their aligned timestamps before chart statistics, title, plotting, and range-bar calculations; sanitize both fresh downloads and existing history-cache records so a trailing `NaN` cannot become the last price
- if no finite stock closes remain, report no historical data instead of rendering or raising

Axis behavior:
- swing: date_form d-m-y + adaptive xfrequency
- intraday:
  - numeric x positions
  - ticks at start/middle/end
  - labels are session times
  - extend intraday to market close with NaN placeholders

Output after chart:
- range stats
- range line
- optional 52W stats + 52W range line when quote fields are available
- explicit last traded/close value line
- move summary
```

## 9) Rebased Table Prompt
```text
Implement table-only mode (`t`) output:
- title: "Rebased Co-Plot (base=100): ..."
- include `[period=<period>, bin=<interval>]`
- include explicit Date Range: start -> end
- columns: Date, Stock, Bench, Delta, Alpha%
- Alpha% definition: `((Stock / Bench) - 1) * 100` on rebased values
- final relative line at bottom
- final Alpha% line at bottom
- colorize numbers by sign (delta)
- keep table rows unsampled so row spacing always matches the header bin (for example `bin=5m` means 5-minute rows, `bin=1wk` means weekly rows)

Rules:
- no chart in `t` mode
- if 2y with monthly interval, prefer 24 rows (monthly granularity)
```

## 10) Index Board Prompt
```text
Implement:
- `index`: live quote board
- `index list`: catalog only
- `snap`: constituent stock snapshot for supported board index modes
- Visually highlight the first three `NIFTY 50` columns (`Index`, `Ticker`, `Price`) in `index` output for quick scanning in sorted rows.

Default sections:
1) India (exclude Sensex)
- NIFTY 50
- NIFTY BANK
- NIFTY IT
- NIFTY MIDCAP 100
- NIFTY MIDCAP SELECT
- NIFTY NEXT 50
- NIFTY INFRA
- NIFTY PSE
- NIFTY AUTO
- NIFTY ENERGY
- NIFTY DEFENCE
- NIFTY FMCG
- NIFTY MEDIA
- NIFTY METAL
- NIFTY MNC
- NIFTY PHARMA
- NIFTY PSU BANK
- NIFTY REALTY
- NIFTY FIN SERVICE
- NIFTY CONSUMPTION
- INDIA VIX
- NIFTY SMALLCAP 100

2) Global
- FTSE 100
- CAC 40
- HANG SENG
- NIKKEI 225
- NASDAQ
- DOW JONES

Board columns:
- Index, Ticker, Price, Change, Range
- Keep row columns visually aligned with fixed-width formatting that is ANSI-color-safe.

Board sorting:
- Same movement ordering as snap: greens first (largest gain to smallest), then reds (smallest fall to largest), then unknowns.
- Use canonical index symbols for PSE/PSU BANK (`^CNXPSE`, `^CNXPSUBANK`) to avoid stale synthetic series.
- For index boards, run one unified three-pass batch cycle across India+Global symbols, then per-symbol fallback only for unresolved rows.
- Group snapshot fetches use two intraday minute sessions (`2d`, `1m`) as the primary price/range/previous-close source, requesting daily batch candles (`5d`, `1d`) only for symbols with incomplete minute data.
- Split grouped snapshot universes into stable, order-preserving batches of at most 20 symbols and pass `threads=False` to yfinance downloads so large indices do not create rate-limit-prone concurrent request bursts.
- Partition grouped symbols by exchange session: open symbols use uncached minute batches; closed symbols use daily-close batches cached per symbol under the latest completed session date.
- Before caching a closed-market daily snapshot, compare its candle date with the expected completed session; when the daily endpoint lags, replace it with the final minute-session snapshot and normalize that result as EOD.
- Keep pre-open and post-close EOD cache keys distinct when they refer to different completed sessions on the same local calendar day.
- Derive grouped previous close from the final bar of the prior minute session when available, falling back to the daily series with awareness of whether its last row is today's partial candle; restrict live price and day range to the latest minute session.
- During market hours, grouped views should use the batch minute-bar surface as the primary live path; retry missing symbols in later batch passes instead of switching to per-symbol quote fetches.
- For known indices, keep one canonical app symbol and one explicit Yahoo fetch symbol; avoid runtime probe lists for stable mappings.
- Grouped snapshot outputs (`index`, `snap`, watchlist snapshots) should keep freshness inline with the title/header: `India (Live prices as of HH:MM)` or `Snap: ... (Live prices as of HH:MM)`, else `... (EOD data as of DD-MM-YY)`.
- In `index` board resolution, skip quote-based day-range enrichment during candidate selection; compute missing ranges in render path via intraday fallback.
- If grouped batch resolution returns no row at all for an index-board entry, do one direct quote fetch for that row before rendering `n/a`.
- If range is still missing in `index` board but `regularMarketPrice` and `regularMarketPreviousClose` exist, render a proxy range using `min(prev,last)` to `max(prev,last)`.
- If `regularMarketPreviousClose` is missing but quote payload has `regularMarketChange` and `regularMarketChangePercent`, render change from those direct fields in index board rows.
- If batch snapshot lacks both previous-close and direct-change fields for an index row, do one targeted quote fetch for that row to backfill change before rendering `n/a`.
- Support shorthand nickname inference for index symbols (for example: `bank`, `pharma`, `infra`, `fmcg`, `metal`, `media`, `realty`, `energy`, `defence`/`defense`).
- Include `cpse` as a shorthand alias for `NIFTY PSE` (`^CNXPSE`).
- Keep grouped retry policy consistent across multi-symbol quote surfaces (`index`, `snap`, and future grouped views): pass1 full batch, pass2/3 missing-only batch retries with 1s/2s large-universe backoff, then render unresolved rows as unavailable.
- Keep preferred Yahoo fetch mappings explicit and data-backed:
  - `^CNXMIDCAP` -> `NIFTY_MIDCAP_100.NS`
  - `^NIFTYNXT50` -> `NIFTY_NEXT_50.NS`
  - `^NSESMCP100` -> `NIFTY_SMLCAP_100.NS`
  - `^CNXDEFENCE` -> `NIFTY_IND_DEFENCE.NS`
  - Do not retain runtime probe lists for other indices when canonical symbols already return stable batch data.
- For grouped fetch surfaces, show hash-only TTY activity (`#` on each network call) with no descriptive progress text.

Range behavior:
- Prefer quote payload day low/high.
- If missing for an index, derive day range from best-effort intraday history fallback.
- For grouped index/snap fetches, enrich missing day low/high from per-symbol quote payload before rendering range lines.
- For index board rows, if range is still missing, retry quote day low/high using both resolved fallback symbol and canonical index symbol.

snap behavior:
- Works only for Indian board indices (except `INDIA VIX`) and `DOW JONES`.
- Show Symbol, Price, Change, and per-row day-range line for all configured constituents.
- When a supported index has no configured constituent universe, fall back to one index-only row instead of failing.
- Keep Symbol/Price/Change/Range columns visually aligned with ANSI-color-safe fixed widths.
- Sort rows with greens first (largest gain to smallest), then reds (smallest fall to largest), with no separator.
- Source constituents from `data/index_constituents.csv` so updates are data-only and do not require CLI code edits.
- Regenerate India index constituent universes from Nifty public EquityStockWatch feeds (via `iislliveblob.niftyindices.com`) to keep lists complete.
- Keep global snap constituents only for enabled global indices (currently `DOW JONES`).
- For indices with known fixed membership sizes, show configured vs expected count and warn when local CSV data is incomplete.
- Use shared group fetch policy: pass1 full batch, pass2/3 missing-only batch retries, then render unresolved rows as unavailable.
- Print `Snap fetch passes used: <n>` at the end of snap output.

moves behavior:
- Works in watchlist mode and for active index symbols with configured constituents.
- Canonical command is `move`; keep `moves` as an alias.
- Supports explicit override grammar: `move on <code1> <code2> ... [period]` (alias: `moves on ...`).
- Supported periods: `Nd`, `Nmo` where `N < 12`, and `Ny` (default `1mo`). Convert the normalized period to its corresponding move-dot count instead of falling back to 30 dots for custom periods such as `2d`.
- Render one move-dot row per symbol with an `Up Days` value (`green days / requested dots`) and sort rows by green-day count descending (max green days first).
- For index symbols without configured constituent universe, fall back to a single row for the index symbol itself.

trend behavior:
- Works in watchlist mode and for active index symbols with configured constituents.
- Canonical command is `trend`; keep `trends` as an alias.
- Supports explicit override grammar: `trend on <code1> <code2> ...` (alias: `trends on ...`).
- Render one trend-score row per symbol and sort rows by trend score descending.
- For index symbols without configured constituent universe, fall back to a single row for the index symbol itself.
- On index alias symbol switches, if Yahoo `Ticker` quote is sparse, build quote-like payload from grouped snapshot fetch so quote view still renders.
- If index quote fallback is still unavailable, keep the symbol switch to index mode and print a warning instead of rejecting the switch.

relret behavior:
- Works in watchlist mode and index/constituent contexts.
- Supports explicit override grammar: `relret on <code1> <code2> ... [period] [vs <benchmark> [period]]`.
- Supported periods: `7d`, `1mo`, `3mo`, `6mo`, `9mo`, `1y` (default `1mo`).
- Show symbol return, benchmark return, and relative return; sort stock rows by strongest outperformance first.
- In watchlist mode, append a final `WATCHLIST(EW)` row for equal-weight watchlist return vs benchmark, with one blank separator line before it.
- In index mode, canonicalize fallback index symbols to primary index tickers before benchmark history fetch (for example `NIFTY_NEXT_50.NS` -> `^NIFTYNXT50`).
- Benchmark policy is mode-specific: watchlist mode uses `^NSEI`; index mode uses the active index symbol itself.
- For explicit `relret on ...`, override context scope and use fixed benchmark `^NSEI` (NIFTY 50).
- `vs <benchmark>` overrides any default benchmark policy for the current command.

corr behavior:
- Works in watchlist mode and index/constituent contexts.
- Supports explicit override grammar: `corr on <code1> <code2> ... [period]`.
- Supported periods: `1mo`, `3mo`, `6mo`, `9mo`, `1y` (default `1mo`).
- Build daily return series on overlapping timestamps; require at least two symbols.
- Render compact sections only: top positive pairs, top negative pairs, and near-zero diversifier pairs.
```

## 11) REPL Controller Prompt
```text
Implement REPL controller with:
- command dispatch order (help/index/t/cc/c/period-shortcut/symbol switch)
- persistent history via readline + local history file
- `cache` command that prints today's persisted history-cache summary (path, counts, symbols, dimensions)
- `cache clear` command that clears only today's persisted history cache bucket
- `news <code>` command that resolves one symbol and prints recent Yahoo headlines
- `moves [period]` command for watchlist/index contexts with default `1mo`
- `moves on <code1> <code2> ... [period]` explicit symbol override for move-dot board
- `trend` command for watchlist/index contexts
- `trend on <code1> <code2> ...` explicit symbol override for trend-score board
- `relret [period]` command for watchlist/index contexts with default `1mo` (alias `rr`)
- `relret [period] [vs <benchmark> [period]]` command for watchlist/index contexts with default `1mo`
- `relret on <code1> <code2> ... [period] [vs <benchmark> [period]]` explicit symbol override for relative-return board
- `corr [period]` command for watchlist/index contexts with default `1mo`
- `corr on <code1> <code2> ... [period]` explicit symbol override for correlation board
- prompt updates on active symbol changes
- clear stderr messages for invalid commands
- refresh semantics:
  - `reload` (canonical) = refresh active quote + replay last non-quote view (`c`/`cc`/`t`/`tt`)
  - `r` = alias of `reload`
- interrupt semantics:
  - `Ctrl+C` during command execution cancels the active command without exiting REPL
  - `Ctrl+C` while waiting on prompt exits REPL

Important:
- Keep `c` and `cc` separate by design.
- Shortcut bare period token should trigger swing chart.
```

## 12) Test Suite Prompt (No-Network Core)
```text
Add parser/validator tests that do not fetch live data.

Minimum test matrix:
- t:
  - `t - 2y`
  - `t - 2y mo`
  - `t - 3mo w`
  - `t nifty`
  - `t nifty - 3mo w`
- tt:
  - `tt`
  - `tt 15m`
  - `tt 30m`
  - `tt 1hr`
  - `tt nifty`
  - `tt nifty 5m`
  - `tt nifty 1hr`
  - `tt - 15m`
  - `tt nifty - 30m`
- c:
  - `c - 2y`
  - `c - 2y mo`
  - `c nifty - 3mo w`
- cc:
  - `cc`
  - `cc 1m`
  - `cc 30m`
  - `cc 1hr`
  - `cc nifty 5m`
  - `cc nifty 1hr`
  - invalid token rejection
- validator:
  - reject 1m with >7d
  - reject intraday with max
  - allow weekly for 2y

Command:
- `make test` (preferred; prints only `<test_id> PASS|FAIL` lines plus one final `TOTAL/PASS/FAIL` summary while enforcing 95% `src/tickertrail/cli.py` coverage gate)
- `PYTHONPATH=src uv run --no-sync python -m coverage run -m unittest discover -s tests -q && PYTHONPATH=src uv run --no-sync python -m coverage report -m --fail-under=95 --include="src/tickertrail/cli.py"`

Coverage requirement:
- keep `src/tickertrail/cli.py` at or above 95%
```

## 13) Integration Sanity Prompt (Network Optional)
```text
Run scripted REPL smoke checks:
- `h`
- `index`
- `index list`
- symbol switch
- `t - 2y mo`
- `c - 2y mo`
- `cc 5m`

If network fails:
- explicitly state environment/network limitation
- still validate parser and non-network tests
```

## 14) Review Prompt (Hard-Nosed)
```text
Do a code review focused on:
- parser ambiguity
- branch explosion in REPL
- dead code
- inconsistent unit semantics (m vs mo)
- hidden network calls in pure layers
- missing validation usage paths
- mismatch between help and behavior
- inadequate tests for grammar edge cases

Output:
- findings ordered by severity
- file:line references
- concrete fixes
```

## 15) Final Delivery Prompt
```text
Prepare final summary with:
1) what was built
2) exact command grammar supported
3) known limitations
4) tests executed and results
5) next hardening steps (if any)

Keep it concise and factual.
```

## 16) Determinism Rules (Always Apply)
- Keep parser behavior deterministic and explicit.
- Avoid silent fallback that changes user intent.
- Never infer `m` as month.
- Keep user-facing formats stable once accepted.
- If behavior changes, update help and tests in same patch.
- REPL should tolerate pasted prompt fragments like `tt>...> command` by extracting the trailing command token.
- Dispatch bare and trailing `?` before configuration, command, symbol, benchmark, cache, subprocess, or network handling so situational help can never execute the inspected prefix.
- Keep REPL controller state explicit: active symbol/watchlist prompt context should move together, and last-view replay metadata should use typed state instead of ad-hoc string/dict pairs.
- Grouped snapshot views (`index`, `snap`, watchlist snapshots, index fallback quote payloads) should use uncached batch minute-bar data only for currently open exchanges, then use session-keyed persisted daily-close snapshots for closed exchanges.
- During grouped market-hours fetches, do not use cached data; fetch large universes in sequential batches of at most 20 symbols with download threading disabled, then retry missing symbols via later passes only after a short bounded backoff.
- Daily analytics commands that depend on the latest point (`move`, `trend`, `relret`, `corr`, and derived current-period calculations) should overlay the current batch minute-market price onto the last daily history point while the market is open; when the market is closed they should stay on EOD history/cache data.
- Daily analytics commands that use the live overlay should print one explicit freshness line with wording that matches the semantics:
  - `move`: `Latest point overlaid with live price as of HH:MM`
  - `trend`: `Trend scores include live price overlay as of HH:MM`
  - `relret`: `Relative returns include live price overlay as of HH:MM`
  - `corr`: `Correlations include live price overlay as of HH:MM`
- Local CSV loaders (symbol universe/constituents) must handle `OSError` gracefully and fail soft.
- For every command, print a final network footer line: total calls plus API breakdown (e.g. yfinance surfaces).
- Footer must also include per-command history-cache stats (`hits` / `misses`) on the same line.
- Persist history-cache JSON files under repository-local `.cache/history/` (never global user cache paths).
- Keep intraday `close_points` cache freshness interval-aware with short TTLs (instead of stale-until-midnight), while preserving same-day caching for non-intraday history payloads.
- Quote range bars (`Day Range`, `52W Range`) should compute width from terminal columns so range rows remain single-line on typical narrow terminals.
- Chart footer range rows should also be single-line (`Day Range` and optional `52W Range` with bar + bounds) to reduce vertical clutter.

## 17) Definition of Done
- Commands match frozen contract in section 0.
- `plotext` config matches section 8.
- `index` and `index list` implemented.
- parser + validator tests green.
- coverage at or above 95% for `src/tickertrail/cli.py`.
- docstrings and major-block comments present.
- help output and behavior are aligned.

## 18) Index Day-Range Fallback Rules
- For grouped index/snap views, treat Yahoo day-range as available from any of:
  - `regularMarketDayLow` + `regularMarketDayHigh`
  - `dayLow` + `dayHigh`
  - textual `regularMarketDayRange` or `dayRange` formatted as `low - high`
- Continue using three batch download passes first; use quote fallback only for unresolved or range-enrichment cases.
- If all supported quote/range fields are absent, render `Range` as `n/a` instead of synthesizing fake bounds.

## 19) Upstox F&O Option-Chain Prompt
```text
Implement a read-only stock/index option-chain workflow backed only by the Upstox APIs.

Configuration:
- `config` enters `tt>config>` from the normal REPL.
- Keep configuration mode flat: `token add upstox <token>` saves immediately; do not open another interactive token prompt.
- Keep token-status reads out of configuration mode. `show token` and `show token upstox` report status and path from a normal prompt but never echo the token.
- `end` and `exit` return directly to `tt>`; `?`, `help`, and `help token` are situational and network-free.
- Persist the stripped token atomically in repository-local `.upstox_analytics_token`, chmod `0600`, and list that file in `.gitignore`.

Chain grammar:
- Stock/index context: `chain|oc [near|next|far|month] [strikes <1-25>]`.
- Stock/index context exact date: `chain|oc expiry YYYY-MM-DD [strikes <1-25>]`.
- Any prompt can use `chain|oc <symbol|index> ...` for an explicit target.
- Keep `chain ?`, `oc ?`, and `help chain` situational: stock/index prompts show only contextual forms without a redundant target; root/watchlist prompts show only explicit target forms.
- Defaults: `near`, 10 strikes below and 10 strikes above ATM.
- Resolve every target through `/v2/instruments/search` with NSE/BSE and EQ/INDEX filters. Require an exact ticker, name, or short-name identity; prefer the exchange implied by `.NS`/`.BO`, otherwise prefer NSE. Reuse TickerTrail's index aliases before search.
- Validate every request through `/v2/option/contract` without an expiry filter. `near`, `next`, and `far` are the first three actual future expiry dates; `month` is the first future contract date marked non-weekly; an exact date must be listed. Empty contracts mean the stock/index is not currently an F&O underlying. Do not send static relative keywords directly to the chain endpoint because a calendar week with no remaining expiry can return an empty chain.

Strike-detail grammar:
- Stock/index context: `opt|option <strike> [near|next|far|month]`.
- Stock/index exact date: `opt|option <strike> expiry YYYY-MM-DD`.
- Root/watchlist explicit forms: `opt|option <symbol|index> <strike> ...`.
- Keep `opt ?`, `option ?`, and `help opt` situational in the same manner as chain help.
- Defaults: `near`, with both CE and PE displayed. Never inherit the previously viewed chain expiry.
- Accept positive finite strikes with grouping commas or decimals. Require an exact listed strike for the resolved expiry; never silently choose the nearest strike. On failure, suggest up to three nearby listed strikes.

API/data boundaries:
- Fetch the chain from `/v2/option/chain` using the resolved underlying instrument key and selected expiry value.
- Preserve `lot_size` per expiry from the existing `/v2/option/contract` response and show it on the ATM metadata line. Do not add another request; render `n/a` if the selected expiry has no single valid positive whole-number lot size.
- Send an explicit stable TickerTrail `User-Agent` on every HTTP request so gateway policy does not classify the default Python urllib signature as banned.
- Fetch the underlying LTP/previous close from `/v3/market-quote/ltp`; if this header quote fails but the chain has an underlying spot, render using that spot.
- For `opt`, retain each side's instrument key, bid/ask prices and quantities, previous OI, and complete Greek set from the existing option-chain response. After selecting the exact strike, replace the chain command's underlying-only LTP call with one `/v2/market-quote/quotes` request batched across the underlying, CE, and PE keys. Use it for current-session OHLC range bars and the underlying header. A failed grouped quote must leave chain-derived detail usable and render unavailable ranges as `n/a`.
- Never silently switch the chain to Yahoo or another provider.
- Normalize malformed/missing scalar fields to `n/a` and return concise safe errors for network, token, gateway, and response failures. Preserve Cloudflare/gateway details from structured error payloads; never label every HTTP 403 as a rejected token.

Rendering contract:
- Top line: resolved stock/index name and value plus signed absolute and percentage daily move; the metadata line includes ATM, selected-expiry lot size, strike-window size, update time, and provider.
- Calls on the left, strike spine in the center, puts on the right.
- Always sort the strike spine descending so higher strikes are at the top.
- Make both header rows bold, every strike-spine cell bold, and the complete ATM row bold.
- Color each call and put half independently green/red based on LTP versus previous close; use neutral gray when change cannot be calculated.
- Show LTP as `<price> (<signed-percent>%)`; put Delta immediately beside LTP.
- Also show Theta, volume, and OI. Omit IV, Gamma, and Vega so the table remains compact, targeting at most 120 columns for typical values.
- Select the nearest available strike as ATM; on an exact-distance tie choose the lower strike.
- The `opt` view uses a vertical call-versus-put comparison rather than a wide chain row. Render three independently scaled 40-character day-range bars for the underlying, CE, and PE, with the current value clamped to the displayed range. Clearly label every bar because their scales differ.
- Group detail rows under `PRICE & LIQUIDITY`, `RISK & GREEKS`, and `VALUE AT CURRENT PREMIUM`. Show LTP with absolute/percentage daily movement, best bid/ask with quantity, midpoint-relative spread, volume, OI, OI change, IV, Delta, Gamma, Theta, Vega, moneyness, intrinsic/time value, premium per lot, and expiry breakeven.
- Premium per lot is `LTP * lot_size`; call/put intrinsic values are `max(spot-strike, 0)` and `max(strike-spot, 0)`; time value is `LTP-intrinsic`; long-premium expiry breakevens are `strike+call LTP` and `strike-put LTP`. Do not imply fees, taxes, slippage, margin, position-side economics, or trade recommendations.
- Use semantic ANSI colors redundantly with text: green for positive movements/OI change and bids, red for negative movements/OI change and asks, yellow for ATM/spreads/IV/breakevens, cyan for structure, and gray for `n/a`. Preserve signs, arrows, labels, and range endpoints when color is disabled. Leave Greeks neutral because their signs are not inherently favorable without a position.

Testing:
- Mock every Upstox request; unit tests must make no live network calls.
- Cover every qualifier, actual-contract expiry selection, exact-date and strike-count validation, request identity, token/gateway errors, response normalization, quote fallback, command routing/help, and ANSI rendering semantics.
- Cover contextual and explicit `opt` grammar, comma/decimal strikes, exact-date selection, invalid-strike suggestions, extended option-side normalization, grouped full-quote mapping, full-quote fallback, all derived calculations, range bars, semantic ANSI colors, situational help, and the fixed four-request count.
```

## 20) Upstox Company Fundamentals Prompt
```text
Implement a read-only consolidated company-fundamentals dashboard backed only by Upstox.

Grammar and context:
- Canonical command: `fundmentals` (retain this exact accepted spelling).
- Alias: `funda`.
- Accept no target, statement-type, period, or other qualifiers.
- Make both forms available only with an active listed stock at `tt>stock><symbol>>`.
- Keep bare `?`, `fundmentals ?`, `funda ?`, and `help fundmentals` network-free and context-aware. Root, index, watchlist, and config situational help must not advertise the command as executable.
- Default permanently to consolidated statements for this grammar.

API and normalization:
- Resolve the active stock exactly through Upstox instrument search and extract its ISIN; reject indices and non-equity instruments.
- Fetch key ratios, quarterly income statement, yearly income statement with full statement, cash flow, full consolidated balance sheet, shareholdings, corporate actions, and current LTP.
- Use the API's operating cash-flow summary as CFO; do not label investing cash flow or another proxy as FCF.
- Normalize ratio strings with or without `%`, malformed fields, missing histories, and absent sector values safely to `n/a`.
- Treat LTP as optional: statement data must still render when price retrieval fails, while price-derived metrics become `n/a`.
- Render every history period and corporate-action event returned by Upstox and print the actual counts. Do not promise 8–10 years; validation in August 2026 returned four quarters, four annual income/cash-flow years, four balance-sheet years, and four shareholding quarters for representative stocks.

Metrics:
- Direct: P/E, P/B, ROE, ROCE, latest annual CFO, quarterly sales/operating profit/PAT, annual PAT/CFO, balance-sheet line items, shareholding, dividends, and non-dividend corporate actions.
- OPM*: quarterly operating profit divided by quarterly revenue.
- PAT Margin*: quarterly PAT divided by quarterly revenue.
- PEG*: P/E divided by the latest three-year diluted-EPS CAGR, requiring four positive EPS observations and positive growth; fall back to basic EPS only when diluted EPS is absent.
- Book value/share*: current Upstox price divided by P/B.
- Dividend yield TTM*: sum of returned dividends with ex-dates inside the trailing 365 days divided by current price.
- Mark valuation-derived metrics with `*` and disclose their formulas below the tables; render OPM and PAT Margin as clearly named percentage rows.
- Allow sector-specific ratio omissions, especially ROCE for banks, without failing the dashboard.

Rendering:
- Heading: symbol/name, `FUNDAMENTALS`, consolidated basis, units, IST update time, and Upstox attribution.
- Bold section/table headers.
- Sections in order: `VALUATION & QUALITY`, `QUARTERLY PERFORMANCE`, `ANNUAL PROFIT & CASH FLOW`, `BALANCE SHEET`, `SHAREHOLDING`, `DIVIDEND HISTORY`, and finally `CORPORATE ACTIONS`.
- Quarterly rows: Sales, Sales QoQ, Operating Profit, OPM, PAT, PAT QoQ, PAT Margin.
- Annual rows: PAT, PAT YoY, CFO, CFO YoY.
- Balance-sheet rows: Total Assets, Equity, Current Assets, Current Liabilities, Net Current Assets.
- Keep dividends in their dedicated table. The final corporate-actions table contains only non-dividend events such as bonus, split, and rights; render an explicit empty row when none are returned.
- Color positive changes green, negative changes red, and zero neutral when ANSI output is available.
- Monetary statement values are INR crore; per-share values use rupees.

Architecture and tests:
- Put data models, injected-request fetching, normalization, calculations, and rendering in `fundamentals.py`; do not expand `cli.py` with the dashboard implementation.
- Track each real Upstox request in the standard per-command network footer.
- Mock every network request in tests. Cover fixed request parameters, four-period normalization, margin and valuation derivations, balance-sheet data, separated/final corporate actions, sparse/malformed data, optional-price failure, company-only scope, rendering/color semantics, exact REPL routing, no-qualifier rejection, aliases, and situational help.
```
