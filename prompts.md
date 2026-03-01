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
  - no active symbol: `tickertrail> `
  - active symbol: `tickertrail><symbol_stem_lowercase>> `
  - examples: `tickertrail>bel> `, `tickertrail>bankbaroda> `
- Date format in user output: `dd-mm-yy`.

Core commands:
- `h` / `help [topic|command]`: organized command reference with examples; topic shortcuts include `core`, `chart`, `table`, `watchlist`, `index`, and `help <command>` prints detailed usage/defaults/examples for that command.
- `quote` / `q`: print quote for current symbol/index context (disallow in watchlist mode).
- `quit` / `exit`: leave REPL.
- `cls`/`clear`: clear terminal screen (must not trigger symbol resolution).
- `!<shell-cmd>`: pass command to underlying shell from REPL.
- `reload` / `r`: refresh active quote and replay last chart/table view.
- `cd ..`: return to the last exited index/watchlist mode without symbol re-resolution.
- `index`: live market board with India + Global sections.
- `index list`: curated index universe (symbol catalog) without live fetch.
- `news <code>`: resolve symbol and print latest Yahoo Finance headlines (best-effort availability per ticker/region).
  - Render publish time in local timezone with relative age when available; parse timestamp fields from both top-level items and nested `content` payloads.
  - Keep output compact: `* (age) headline` plus link on next line, one blank line between items, no source row.
  - Keep colors subtle and terminal-safe: cyan headline line + gray link line when ANSI color is available.
  - Accept index aliases as `<code>` so `news` works for common index names (`nifty`, `it`, `metals`, `consumer`, `dow`).
- `snap`: constituent price snapshot for supported active board index symbols.
- `watchlist create <name>` / `wl create <name>`: create local watchlist.
- `watchlist list` / `wl list`: list local watchlists.
- `watchlist delete <name>` / `wl delete <name>`: delete local watchlist.
- `watchlist merge <wl1> <wl2> <target>` / `wl merge <wl1> <wl2> <target>`: union two source watchlists into target (create target if missing; preserve stable de-dup order).
- `watchlist open <name>` / `wl open <name>`: enter watchlist mode (prompt becomes `<name>> `).
- `watchlist <name>` / `wl <name>`: shorthand for `watchlist open <name>`.
- `watchlist`: exit watchlist mode.
- bare `wl`: alias for `wl list`.
- while in watchlist mode, typing a symbol switches to stock quote mode and exits watchlist mode.
- after leaving index/watchlist mode via symbol switch, `cd ..` returns to that last mode context with no symbol re-resolution.
- `add <code...>`: add validated stock codes in active watchlist mode.
  - when a symbol already exists in the active watchlist, print an explicit "already exists" message.
  - validate using local NSE universe data only (no network fetches while adding).
- `delete <code...>`: remove symbols from active watchlist mode.
- `list` in watchlist mode: print symbols in current watchlist.
- `snap` in watchlist mode: show snapshot for symbols in that watchlist.
- `move [7d|1mo|3mo|6mo|9mo|1y]` in watchlist mode: show move-dot rows for all symbols (`moves` alias supported; default `1mo`).
- `move on <code1> <code2> ... [7d|1mo|3mo|6mo|9mo|1y]`: explicit symbol override for `move`/`moves`.
- `trend` in watchlist mode: show current trend-score rows for all symbols (`trends` alias supported).
- `trend on <code1> <code2> ...`: explicit symbol override for `trend`/`trends`.
- `relret [7d|1mo|3mo|6mo|9mo|1y] [vs <benchmark> [7d|1mo|3mo|6mo|9mo|1y]]` in watchlist mode: show relative-return ranking (alias `rr`; default `1mo`).
- `relret on <code1> <code2> ... [7d|1mo|3mo|6mo|9mo|1y] [vs <benchmark> [7d|1mo|3mo|6mo|9mo|1y]]`: explicit symbol override for `relret`.
- `corr [1mo|3mo|6mo|9mo|1y]` in watchlist mode: show return-correlation summary (default `1mo`).
- `corr on <code1> <code2> ... [1mo|3mo|6mo|9mo|1y]`: explicit symbol override for `corr`.
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
- `t <code>`
- `t <code> <period>`
- `t - <period> [agg]`
- `t <code> - <period> [agg]`
- same grammar for `c`
- `cc`, `cc <1m|5m|15m>`, `cc <code>`, `cc <code> <1m|5m|15m>`
- `tt`, `tt <1m|5m|15m>`, `tt <code>`, `tt <code> <1m|5m|15m>`
- `tt - <period> [agg]`, `tt <code> - <period> [agg]`
- canonical equivalents:
  - `chart swing`, `chart swing <code>`, `chart swing <code> <period>`, `chart swing - <period> [agg]`, `chart swing <code> - <period> [agg]`
  - `chart intra`, `chart intra <1m|5m|15m>`, `chart intra <code>`, `chart intra <code> <1m|5m|15m>`
  - `table swing`, `table swing <code>`, `table swing <code> <period>`, `table swing - <period> [agg]`, `table swing <code> - <period> [agg]`
  - `table intra`, `table intra <1m|5m|15m>`, `table intra <code>`, `table intra <code> <1m|5m|15m>`
  - `table intra - <period> [agg]`, `table intra <code> - <period> [agg]`
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

Usability preference:
- Prefer non-dash forms in docs/examples (`c nifty 3mo w`, `t nifty 2y mo`).
- Keep dash forms as advanced variants for explicit structure-preserving intent.

Token conventions:
- period units: `d`, `w`, `mo`, `y`, and `max`
- aggregation units: `m` (minute), `d`, `w`, `mo`
- strict meaning:
  - `m` is always minute
  - `mo` is always month

Persistence conventions:
- Store watchlist data in `data/db.json`.
- JSON shape:
  - top-level object with `watchlists` map
  - watchlist names as keys and de-duplicated symbol arrays as values
```

## 1) Architecture Prompt
```text
Design a small architecture for tickertrail with clear separation:

1) Input grammar layer
- Pure parse functions.
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

3) Render layer
- Quote renderer
- Chart renderer (plotext)
- Table renderer
- Index board renderer

4) REPL/controller layer
- command dispatch
- active symbol state
- prompt string generation

Output expected:
- a short architecture map
- module/function boundaries
- explicit list of pure/testable functions
```

## 2) File Skeleton Prompt
```text
Create minimal file layout:

- src/tickertrail/cli.py
- tests/test_cli_parsing.py
- tests/test_cli_validation.py
- tests/test_cli_prompt_and_format.py

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

Axis behavior:
- swing: date_form d-m-y + adaptive xfrequency
- intraday:
  - numeric x positions
  - ticks at start/middle/end
  - labels are session times
  - extend intraday to market close with NaN placeholders

Output after chart:
- rebased comparison table checkpoints
- range stats
- range line
- move summary
```

## 9) Rebased Table Prompt
```text
Implement table-only mode (`t`) output:
- title: "Rebased Co-Plot (base=100): ..."
- include `[period, interval]`
- include explicit Date Range: start -> end
- columns: Date, Stock, Bench, Delta, Alpha%
- Alpha% definition: `((Stock / Bench) - 1) * 100` on rebased values
- final relative line at bottom
- final Alpha% line at bottom
- colorize numbers by sign (delta)

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
- Group snapshot fetches use daily batch candles (`5d`, `1d`) for price/prev/day-range to reduce call volume.
- Support shorthand nickname inference for index symbols (for example: `bank`, `pharma`, `infra`, `fmcg`, `metal`, `media`, `realty`, `energy`).
- Include `cpse` as a shorthand alias for `NIFTY PSE` (`^CNXPSE`).
- Keep grouped retry policy consistent across multi-symbol quote surfaces (`index`, `snap`, and future grouped views): max three batch attempts, then direct per-symbol `Ticker` fallback.
- During per-symbol `Ticker` fallback, add small random pacing (10-20ms) and adaptive backoff on consecutive misses to reduce throttling.
- Make fallback pacing runtime-configurable via `src/tickertrail/conf.json`:
  - `ticker_fallback_jitter_min`
  - `ticker_fallback_jitter_max`
  - `ticker_fallback_backoff_step`
  - `ticker_fallback_backoff_max`
  - Prefer human-readable duration strings like `10ms`, `20ms`, `50ms`, `200ms`.
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
- Use shared group fetch policy: pass1 full batch, pass2/3 missing-only batch retries, then direct per-symbol `Ticker` fallback for unresolved rows.
- Print `Snap fetch passes used: <n>` at the end of snap output.

moves behavior:
- Works in watchlist mode and for active index symbols with configured constituents.
- Canonical command is `move`; keep `moves` as an alias.
- Supports explicit override grammar: `move on <code1> <code2> ... [period]` (alias: `moves on ...`).
- Supported periods: `7d`, `1mo`, `3mo`, `6mo`, `9mo`, `1y` (default `1mo`).
- Render one move-dot row per symbol and sort rows by green-day count descending (max green days first).
- For index symbols without configured constituent universe, fall back to a single row for the index symbol itself.

trend behavior:
- Works in watchlist mode and for active index symbols with configured constituents.
- Canonical command is `trend`; keep `trends` as an alias.
- Supports explicit override grammar: `trend on <code1> <code2> ...` (alias: `trends on ...`).
- Render one trend-score row per symbol and sort rows by trend score descending.
- For index symbols without configured constituent universe, fall back to a single row for the index symbol itself.
- On index alias symbol switches, if Yahoo `Ticker` quote is sparse, build quote-like payload from grouped snapshot fetch so quote view still renders.

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
  - `tt nifty`
  - `tt nifty 5m`
  - `tt - 2y mo`
  - `tt nifty - 3mo w`
- c:
  - `c - 2y`
  - `c - 2y mo`
  - `c nifty - 3mo w`
- cc:
  - `cc`
  - `cc 1m`
  - `cc nifty 5m`
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
- REPL should tolerate pasted prompt fragments like `tickertrail>...> command` by extracting the trailing command token.
- Local CSV loaders (symbol universe/constituents) must handle `OSError` gracefully and fail soft.
- For every command, print a final network footer line: total calls plus API breakdown (e.g. yfinance surfaces).
- Footer must also include per-command history-cache stats (`hits` / `misses`) on the same line.
- Persist history-cache JSON files under repository-local `.cache/history/` (never global user cache paths).

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
