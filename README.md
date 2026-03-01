# TickerTrail

Terminal-first stock CLI for quotes, charts, benchmarked performance tables, index snapshots, and persistent watchlists.

TickerTrail is India-first (`.NS`/NSE aware) and also supports US/global symbols and benchmarks through its configured market data provider.

## Highlights

- Fast quote view with:
  - current price, day change, day/52W range bars
  - fundamentals (when available)
  - 30D move dots (left -> right, latest on the right)
  - calendar-anchored returns (`7D`, `1MO`, `3MO`, `6MO`, `9MO`, `1Y`)
  - signal block: trend score, RSI(14), volume-vs-20D, max drawdown(1Y), win-rate, best/worst day, skew
- Swing and intraday terminal charts (with benchmark overlay)
- Rebased comparison tables (`t`, `tt`, `cmp`)
- Index board + constituent snapshot (`index`, `index list`, `snap`)
- Persistent local watchlists with mode-based workflow
- Watchlist snapshot includes:
  - sorted movers
  - equal-weight 1D return
  - NIFTY 50 1D benchmark
  - `Alpha` (Equal-Weight minus NIFTY 50)
- REPL shell passthrough: `!<cmd>`
- Command-level network/cache diagnostics (`Network calls: ... | cache: hits=... misses=...`)

## Requirements

- Python `>=3.10`
- [`uv`](https://docs.astral.sh/uv/) recommended

## Install

```bash
git clone https://github.com/vsjha18/tickertrail.git
cd tickertrail
uv sync
```

## Run

### Direct symbol

```bash
uv run tickertrail RELIANCE
uv run tickertrail TCS
uv run tickertrail AAPL
```

### Start REPL

```bash
uv run tickertrail
```

### Non-REPL subcommands

```bash
uv run tickertrail INFY quote
uv run tickertrail RELIANCE chart --period 6mo --interval 1d --width 110 --height 20
```

## REPL Prompt

- No active symbol: `tickertrail> `
- Active symbol: `tickertrail><symbol_stem_lowercase>> `
- Watchlist mode: `<watchlist_name>> `

Date format in output is `dd-mm-yy`.

## REPL Commands

### Core

- `h` / `help [topic|command]`: organized command help (`core`, `chart`, `table`, `watchlist`, `index`) plus command-level pages with usage, defaults, and examples
- `quote` / `q`: show quote for current symbol/index (not available in watchlist mode)
- `quit` / `exit`: leave REPL
- `cls` / `clear`: clear terminal
- `reload`: refresh REPL shell state
- `r`: refresh current quote and replay last chart/table
- `cd ..`: return to previously active index/watchlist mode without re-resolving symbols
- `cache clear`: clear today's persisted history-cache bucket
- `move [7d|1mo|3mo|6mo|9mo|1y]`: directional move-dots board (alias: `moves`, default `1mo`)
- `trend`: current trend-score board (alias: `trends`, no args)
- `relret [7d|1mo|3mo|6mo|9mo|1y]`: relative-return ranking (default `1mo`)
- `corr [1mo|3mo|6mo|9mo|1y]`: correlation summary of daily returns (default `1mo`)
- `news <code>`: recent market headlines for one symbol (best-effort; availability varies by ticker/region)
  - Shows publish time in local timezone plus relative age when timestamp metadata is available.
  - Timestamp extraction checks both top-level and nested news payload fields.
  - Renders newest timestamped headlines first in compact bullets: `(age) headline` + link, separated by one blank line.
  - Applies subtle ANSI coloring for headlines/links when terminal color is supported.
  - Supports index aliases directly (for example: `news nifty`, `news it`, `news metals`, `news consumer`, `news dow`).
- `!<shell-cmd>`: run shell command in underlying shell

### Symbol / Discovery

- `<symbol>`: switch active symbol and print quote
- `code <query>`: fuzzy ticker lookup from local NSE universe data
- `news <code>`: fetch latest symbol headlines

### Index Tools

- `index`: live board for curated India + global indices
- `index list`: curated index symbol catalog
- Includes `NIFTY MIDCAP SELECT` in the India index set (aliases: `midcap select`, `select`)
- `snap`: index-constituent snapshot for active supported index (falls back to index-only snapshot if constituents are unavailable)
- `move [7d|1mo|3mo|6mo|9mo|1y]`: move-dots board for active index (alias: `moves`; constituents when available; otherwise index symbol) (default `1mo`)
- `trend`: current trend-score board for active index (constituents when available; otherwise index symbol)
- `relret [7d|1mo|3mo|6mo|9mo|1y]`: relative-return ranking for active index scope
- `corr [1mo|3mo|6mo|9mo|1y]`: return-correlation summary for active index scope
- Index alias switching now restores quote output via snapshot fallback when index `Ticker` payload is sparse (for example `it`, `nifty`, `metal`, `metals`).
- `index` highlights the first three `NIFTY 50` row columns (`Index`, `Ticker`, `Price`) for quick visual scanning in sorted output.
- `relret` canonicalizes index fallback symbols (for example `NIFTY_NEXT_50.NS` -> `^NIFTYNXT50`) before benchmark history fetch.
- `relret` benchmark policy: watchlist mode always uses `^NSEI` (NIFTY 50); index mode uses the active index itself as benchmark.
- In watchlist mode, `relret` keeps stock rows sorted by outperformance and appends `WATCHLIST(EW)` at the end (not part of sorting), separated by one blank line.

### Chart + Table

Canonical forms:

- `chart swing [<code>] [<period>]`
- `chart swing [<code>] - <period> [agg]`
- `chart intra [<code>] [<1m|5m|15m>]`
- `table swing [<code>] [<period>]`
- `table swing [<code>] - <period> [agg]`
- `table intra [<code>] [<1m|5m|15m>]`
- `table intra [<code>] - <period> [agg]`

Alias forms (fully supported):

- `c` / `cc` map to `chart swing` / `chart intra`
- `t` / `tt` map to `table swing` / `table intra`
- Existing alias grammar remains valid:
  - `c <period>`, `c <code>`, `c <code> <period>`, `c - <period> [agg]`, `c <code> - <period> [agg]`
  - `cc <1m|5m|15m>`, `cc <code>`, `cc <code> <1m|5m|15m>`
  - `t <code>`, `t <code> <period>`, `t - <period> [agg]`, `t <code> - <period> [agg]`
  - `tt <1m|5m|15m>`, `tt <code>`, `tt <code> <1m|5m|15m>`, `tt - <period> [agg]`, `tt <code> - <period> [agg]`

- `cmp <symbol1> <symbol2> [symbolN ...] [period [agg]]`

### Watchlists

Canonical command family is `watchlist ...`; alias `wl ...` is fully supported.

- `watchlist create <name>`
- `watchlist list`
- `watchlist delete <name>`
- `watchlist merge <wl1> <wl2> <target>`
  - if `<target>` exists: merge into existing target
  - if `<target>` does not exist: create and merge
  - deduplicates while preserving stable order
- `watchlist open <name>`
- `watchlist <name>` (shorthand for `watchlist open <name>`)
- `watchlist` (exit watchlist mode)
- bare `wl` means `wl list`

In watchlist mode (`<name>>` prompt):

- `add <code...>`: add symbols (validated via local NSE CSV; no network call for validation)
- `delete <code...>`: remove symbols
- `list` / `ll`: show current symbols
- `snap`: watchlist snapshot board
- `move [7d|1mo|3mo|6mo|9mo|1y]`: move-dots board for all symbols (alias: `moves`; sorted by max green days to least)
- `trend`: current trend-score board for all symbols (sorted highest to lowest trend score)
- `relret [7d|1mo|3mo|6mo|9mo|1y]`: relative-return ranking for all symbols, plus a final `WATCHLIST(EW)` equal-weight summary row (after one blank separator line)
- `corr [1mo|3mo|6mo|9mo|1y]`: return-correlation summary for all symbols

## Token Rules

- Period units: `d`, `w`, `mo`, `y`, `max`
- Aggregation units: `m`, `d`, `w`, `mo`
- `m` means minute; `mo` means month

## Common Examples

```bash
# REPL
uv run tickertrail

# Inside REPL
help move
help watchlist open
code national thermal
news infy
watchlist create swing
watchlist create momentum
watchlist merge swing momentum core
watchlist open core
add tcs infy reliance
list
snap
moves 1mo
trend
relret
corr
c 1y
t nifty 6mo w
cmp nifty goldbees hdfcbank csco 3y w
!pwd
```

## Data + Storage

- Market data source: configured provider
- Local symbol universe: `data/nse_equity_list.csv`
- Index constituents: `data/index_constituents.csv`
- Watchlist DB: `data/db.json`
- History cache (daily JSON buckets): `.cache/history/`

`data/db.json` structure:

```json
{
  "watchlists": {
    "swing": ["TCS.NS", "INFY.NS"],
    "core": ["RELIANCE.NS", "HDFCBANK.NS"]
  }
}
```

## Project Layout

- `src/tickertrail/cli.py`: CLI entrypoint and REPL controller
- `src/tickertrail/timeframe.py`: period/interval normalization
- `src/tickertrail/market_hours.py`: trading-session helpers
- `src/tickertrail/price_history.py`: close-series retrieval
- `src/tickertrail/quote_tools.py`: quote-derived analytics helpers
- `src/tickertrail/snapshot_service.py`: grouped snapshot orchestration
- `src/tickertrail/views.py`: rendering helpers
- `tests/`: unit test suite (network mocked/stubbed)

## Testing

Run full tests with coverage:

```bash
PYTHONPATH=src UV_CACHE_DIR=.uv-cache uv run --no-sync python -m coverage run -m unittest discover -s tests
PYTHONPATH=src UV_CACHE_DIR=.uv-cache uv run --no-sync python -m coverage report -m --fail-under=95 --include="src/tickertrail/cli.py"
```

Current policy target is at least `95%` coverage for `src/tickertrail/cli.py`.

## Notes

- `Ticker.info` and `download/history` can occasionally return partial/missing fields; CLI falls back where possible.
- Intraday availability and index symbol behavior depend on provider data constraints.
- Network latency is usually the largest source of runtime delay.
