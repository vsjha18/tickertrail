# TickerTrail

TickerTrail is a terminal app for tracking stocks and indices, comparing performance, and managing watchlists.

It works well for India-first workflows (`.NS`/NSE aware) and also supports global symbols.

## Quick Start

Install `uv` first (if not already installed):

macOS / Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv --version
```

macOS (Homebrew alternative):

```bash
brew install uv
uv --version
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv --version
```

Then clone and run:

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

## Mode-Aware Behavior

Many commands are context-sensitive. You usually do not need arguments.

### 1) Stock mode (`tickertrail>symbol>`)

- Entered by typing a stock symbol (example: `infy`).
- `quote`, `c`, `cc`, `t`, `tt` run on the active symbol.
- `move`, `trend`, `relret` run on the active symbol.
- `corr` needs at least two symbols, so use `corr on <code1> <code2> ...`.

### 2) Index mode (`tickertrail>index>`)

- Entered by typing an index alias/symbol (example: `nifty`, `it`, `defence`, `^cnxit`).
- If live quote fields are partial, TickerTrail still keeps you in index mode and shows the best available values.
- `snap` shows constituents for supported indices.
- `move`, `trend`, `relret`, `corr` can be run with no arguments:
  - `move` runs over index constituents when available.
  - `trend` runs over index constituents when available.
  - `relret` runs over index constituents with an index-appropriate benchmark.
  - `corr` runs over index constituents and needs at least two valid overlapping series.

### 3) Watchlist mode (`<watchlist-name>>`)

- Entered with `watchlist open <name>`.
- `move`, `trend`, `relret`, `corr` with no arguments run on symbols in that watchlist.
- `snap` shows the current watchlist snapshot.

### 4) Explicit override mode (`on ...`)

- Works from any context.
- `move on <codes...> [period]`
- `trend on <codes...>`
- `relret on <codes...> [period] [vs <benchmark> [period]]`
- `corr on <codes...> [period]`

## Defaults And No-Arg Behavior

### Analytics defaults

- `move` default period: `1mo`
- `trend`: no period argument
- `relret` / `rr` default period: `1mo`
- `corr` default period: `1mo`

### `relret` benchmark defaults

- Watchlist mode: benchmark defaults to `NIFTY 50 (^NSEI)`
- Index mode: benchmark defaults by active index context
- Explicit `relret on ...`: default benchmark is `NIFTY 50 (^NSEI)`
- `vs <benchmark>` overrides default benchmark selection

### Chart/table defaults

- `c` default period: `6mo` (default interval auto-selected from period)
- `t` default period: `6mo` (default interval auto-selected from period)
- `cc` default interval: `5m`
- `tt` default interval: `5m`
- `cmp` default period: `6mo` (with auto interval)

### Common no-arg commands

- `move` -> `move 1mo` in index/watchlist contexts
- `trend` -> trend board for current context (index/watchlist/symbol)
- `relret` / `rr` -> `relret 1mo` for current context
- `corr` -> `corr 1mo` in index/watchlist contexts
- `c` -> swing chart for active symbol (6mo defaults)
- `t` -> rebased table for active symbol (6mo defaults)
- `cc` -> intraday chart for active symbol (`5m`)
- `tt` -> intraday table for active symbol (`5m`)

## Command Output Examples

These snippets are captured from the real CLI renderers with fixed sample data, so the formatting matches actual command output.

### Quote

```text
tickertrail> quote

INFY.NS  Infosys Ltd.  [INR]
Px 1,941.20  Chg +19.80 (+1.03%)  O 1,928.00  L/H 1,918.10/1,952.30
Vol 8.23M  MCap 8.04T  Updated 02-03-26 02:04:28
Day Range  [──────────────────────────●─────────────]  1,918.10 .. 1,952.30
52W Range  [──────────────────────────────────●─────]  1,380.20 .. 2,015.80
30D Moves  oooooooooooooooooooooooooooooo
Returns    7D +0.85%  1MO +4.78%  3MO +18.69%  6MO +46.30%  9MO +92.17%  1Y n/a
Signal     TrendScore 5/5  RSI14 100.0  Vol/20D 1.02x
Risk       MaxDD(1Y) +0.00%  WinRate(1Y) 100.00%
Extremes   Best +0.73% (03-03-25)  Worst +0.09% (28-02-26)  Skew n/a
PE(TTM) 30.80 | PEG 2.10 | ROE 30.20%
```

### Move Board

```text
tickertrail> move on infy tcs reliance 1mo

Moves (1MO) - Explicit symbols
Symbol           1MO Moves    Dots
INFY.NS          1MO Moves    oooooooooooooooooooooooooooooo
TCS.NS           1MO Moves    oooooooooooooooooooooooooooooo
RELIANCE.NS      1MO Moves    oooooooooooooooooooooooooooooo
```

### Trend Board

```text
tickertrail> trend on infy tcs reliance

Trend (Current) - Explicit symbols
Symbol           Trend Score
INFY.NS          5.0/5.0
TCS.NS           5.0/5.0
RELIANCE.NS      5.0/5.0
```

### Relative Return

```text
tickertrail> rr on infy tcs reliance vs nifty 1mo

Relative Return (1MO) - Explicit symbols vs NIFTY 50 (^NSEI)
Symbol               Return      Bench     RelRet
INFY.NS             +15.13%    +12.06%     +3.07%
RELIANCE.NS         +13.24%    +12.06%     +1.18%
TCS.NS              +10.86%    +12.06%     -1.20%
```

### Correlation Summary

```text
tickertrail> corr on infy tcs reliance 1mo

Correlation Summary (1MO) - Explicit symbols
Universe: 3 symbols | overlap points: 29

Most Positive Pairs
TCS.NS <-> RELIANCE.NS               +1.00
INFY.NS <-> RELIANCE.NS              +1.00
INFY.NS <-> TCS.NS                   +1.00

Most Negative Pairs
n/a

Near-Zero Pairs (Diversifiers)
n/a
```

### Snapshot

```text
tickertrail> snap

Snap: NIFTY IT (10 constituents)
Symbol                    Price             Change              Range
TCS.NS                 1,010.00     +0.80 (+0.08%)     [─────●──────]
LTIM.NS                1,070.00     +0.80 (+0.07%)     [──────●─────]
PERSISTENT.NS            920.00     +0.50 (+0.05%)     [──────●─────]
INFY.NS                1,070.00     +0.50 (+0.05%)     [──────●─────]
HCLTECH.NS               940.00     +0.20 (+0.02%)     [──────●─────]
...
Snap fetch passes used: 1
```

### Swing Chart (`c`)

```text
tickertrail> c 6mo

^CNXIT close (6mo, 1d)  +68.71 (+47.72%)
     ┌─────────────────────────────────────────────────────────────────────────┐
246.3┼───────────────────────────────────────────────────────────────────────••┤
     │                                                                •••••••  │
231.7┼────────────────────────────────────────────────────────────•••••────────┤
     │                                                       ••••••            │
217.0┼──────────────────────────────────────────────────•••••──────────────────┤
     │                                            ••••••               ▗▄▄▄▄▞▀•│
202.4┼───────────────────────────────────────•••••───────────────▄▄▄▞▀▀▘───────┤
     └┬───────┬───────┬───────────────┬───────┬───────┬───────────────┬────────┘
   03-09-25 23-09-25 13-10-25     21-11-25  11-12-25 31-12-25     09-02-26
Day Range  [────────────────────────────●─────────────────────]  144.00 .. 212.71
52W Range  [───────────────●──────────────────────────────]  120.00 .. 260.00
Move: +68.71 (+47.72%) | From: 03-09-25 -> 01-03-26
```

### Intraday Chart (`cc`)

```text
tickertrail> cc 5m

^CNXIT close (1d, 5m)  +7.21 (+0.50%)
      ┌────────────────────────────────────────────────────────────────────────┐
1448.3┼────────────────────────────•••─────────────────────────────────────────┤
      │                           ••▀•                                         │
1446.6┼──────•───────────────────▗•────────────────────────────────────────────┤
      │    ••▄••                ••                                             │
1444.8┼───••───▚•───────────────•──────────────────────────────────────────────┤
      │  •▘     ••             •▘                                              │
1435.9┼────────────────••••────────────────────────────────────────────────────┤
      └┬───────────────────────────────────┬──────────────────────────────────┬┘
     05:55                               10:45                            15:30
Day Range  [────────────────────────────●─────────────────────]  1,435.90 .. 1,448.30
52W Range  [───────────────●──────────────────────────────]  120.00 .. 260.00
Move: +7.21 (+0.50%) | From: 05:55 -> 10:00
```

### Swing Table (`t`)

```text
tickertrail> t 1y

Rebased Co-Plot (base=100): ^CNXIT vs NIFTY 50 [period=1y, bin=1mo]
Date Range: 05-04-25 -> 01-03-26
Date           Stock     Bench     Delta    Alpha%
05-04-25      100.00    100.00     +0.00    +0.00%
05-05-25      100.44    100.59     -0.15    -0.15%
04-06-25      100.87    101.17     -0.30    -0.30%
...
Final Relative (Stock - Bench): -1.43
Final Alpha% (Stock vs Bench): -1.37%
```

### Intraday Table (`tt`)

```text
tickertrail> tt 15m

Rebased Co-Plot (base=100): ^CNXIT vs NIFTY 50 [period=1d, bin=15m]
Date Range: 21:45 -> 10:00
Date           Stock     Bench     Delta    Alpha%
21:45         100.00    100.00     +0.00    +0.00%
00:15         100.38    100.43     -0.05    -0.05%
02:45         100.00    100.00     -0.00    -0.00%
...
Final Relative (Stock - Bench): -0.07
Final Alpha% (Stock vs Bench): -0.07%
```

Intraday tables are unsampled: if `bin=5m`, each row advances by 5 minutes.

### Multi-Symbol Compare (`cmp`)

```text
tickertrail> cmp tcs infy reliance 1y w

Compare (base=100): TCS.NS, INFY.NS, RELIANCE.NS [1y, 1wk]
Date Range: 09-03-25 -> 01-03-26
Date            TCS.NS     INFY.NS RELIANCE.NS
09-03-25        100.00      100.00      100.00
18-05-25        103.72      105.19      104.53
27-07-25        106.45      109.45      108.04
...
Final           118.48      126.02      122.63
```

## REPL Basics

- `h` / `help [topic|command]`: help system
- `quote` / `q`: show active symbol/index quote
- `cache`: show today's history cache summary
- `cache clear`: clear today's history cache
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

- Swing chart: `c [<benchmark>] [<period>]`
- Intraday chart: `cc [<benchmark>] [<1m|5m|15m|30m|1hr>]`
- Swing table: `t [<benchmark>] [<period>]`
- Intraday table: `tt [<benchmark>] [<1m|5m|15m|30m|1hr>]`
- Multi-symbol compare: `cmp <symbol1> <symbol2> [symbolN ...] [period [agg]]`

Period and aggregation tokens:
- Period units: `d`, `w`, `mo`, `y`, `max`
- Aggregation units: `m`, `d`, `w`, `mo`
- `m` means minute, `mo` means month

Override examples (`t/c/cc/tt`):
- Active symbol stays the same; first positional token is benchmark override.
- Change only bin size: `t - w`, `c - mo`, `cc - 15m`, `tt - 30m`
- Change benchmark + bin size: `t bank - w`, `c nifty - mo`, `cc bank - 15m`, `tt bank - 30m`
- Change period + bin size (swing only): `t - 1y mo`, `c - 2y w`

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
  - `move` period accepts `Nd`, `Nmo` (`N < 12`), or `Ny` (for example `5d`, `2mo`, `3y`).
- `trend`
- `trend on <code1> <code2> ...`
- `relret [period]`
- `rr [period]`
- `relret [period] [vs <benchmark> [period]]`
- `relret on <code1> <code2> ... [period] [vs <benchmark> [period]]`
  - `relret` period accepts `Nd`, `Nmo` (`N < 12`), or `Ny` (for example `5d`, `2mo`, `3y`).
- `corr [period]`
- `corr on <code1> <code2> ... [period]`
  - `corr` period accepts `Nd`, `Nmo` (`N < 12`), or `Ny` (for example `5d`, `2mo`, `3y`).

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

- Some symbols/intervals can return partial market data.
- Intraday availability can vary by symbol and market session.
- `cc 1m` and `cc 5m` can differ slightly because of timing and data availability.
- Quote `Day Range` and `52W Range` are rendered as terminal-friendly bars.
- You can also start directly with a symbol, for example:

```bash
uv run tickertrail RELIANCE
```
