# TickerTrail

TickerTrail is a terminal app for tracking stocks and indices, comparing performance, and managing watchlists.

It is optimized for India-first workflows (`.NS`/NSE aware) and also supports global symbols.

## Quick Start

```bash
git clone https://github.com/vsjha18/tickertrail.git
cd tickertrail
uv sync
uv run tickertrail
```

## What You Can Do

- Check live quote snapshots
- View swing and intraday charts in terminal
- Compare stocks vs benchmark (`cmp`, `t`, `tt`)
- Open index boards and constituent snapshots (`index`, `snap`)
- Build and manage persistent watchlists
- Run analytics boards (`move`, `trend`, `relret`/`rr`, `corr`)

## Daily Usage

1. Start REPL:

```bash
uv run tickertrail
```

2. Enter a symbol or index alias:

```text
reliance
nifty
bank
```

3. Run analytics and charts:

```text
quote
c 6mo
t 1y
move 1mo
trend
relret 3mo
corr 6mo
```

## REPL Basics

- `h` / `help [topic|command]`: help system
- `quote` / `q`: show active symbol/index quote
- `reload` / `r`: refresh quote and replay last chart/table
- `cd ..`: return to previous index/watchlist context
- `cls` / `clear`: clear terminal
- `quit` / `exit`: leave REPL
- `!<shell-cmd>`: run shell command

## Symbol and Index Commands

- `<symbol>`: switch active symbol and print quote
- `code <query>`: fuzzy ticker lookup from local universe
- `news <code>`: recent headlines for a symbol/index alias
- `index`: index board
- `index list`: supported index catalog
- `snap`: snapshot for active index/watchlist context

## Charts and Tables

- Swing chart: `c [<symbol>] [<period>]`
- Intraday chart: `cc [<symbol>] [<1m|5m|15m>]`
- Swing table: `t [<symbol>] [<period>]`
- Intraday table: `tt [<symbol>] [<1m|5m|15m>]`
- Multi-symbol compare: `cmp <symbol1> <symbol2> [symbolN ...] [period [agg]]`

Token reminders:
- Period units: `d`, `w`, `mo`, `y`, `max`
- Aggregation units: `m`, `d`, `w`, `mo`
- `m` means minute, `mo` means month

## Watchlists

Top-level:
- `watchlist create <name>`
- `watchlist list`
- `watchlist open <name>`
- `watchlist delete <name>`
- `watchlist merge <wl1> <wl2> <target>`
- `watchlist` (exit watchlist mode)

Inside watchlist mode (`<name>>`):
- `add <code...>`
- `delete <code...>`
- `list` / `ll`
- `snap`
- `move [period]`
- `move on <code1> <code2> ... [period]`
- `trend`
- `trend on <code1> <code2> ...`
- `relret [period]`
- `rr [period]`
- `relret [period] [vs <benchmark> [period]]`
- `relret on <code1> <code2> ... [period] [vs <benchmark> [period]]`
- `corr [period]`
- `corr on <code1> <code2> ... [period]`

## Example Session

```text
help
code national thermal
watchlist create swing
watchlist open swing
add tcs infy reliance
snap
move 1mo
trend
relret
corr
c 1y
t nifty 6mo w
```

## Data Files (User-Relevant)

- Watchlists are stored locally in `data/db.json`
- Local symbol universe file: `data/nse_equity_list.csv`
- Index constituent mapping: `data/index_constituents.csv`
- Local history cache: `.cache/history/`

## Notes

- Some data fields can be partially available depending on symbol/interval.
- Intraday availability can vary by symbol and market session.
- Optional direct-start mode (without entering REPL first) is supported, for example:

```bash
uv run tickertrail RELIANCE
```
