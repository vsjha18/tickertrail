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

## Command Output Examples

These are representative REPL snippets so users can see output shape before running commands.

### Quote

```text
tickertrail> reliance
RELIANCE.NS | Reliance Industries Ltd.
Price: 2,875.40  (+18.20, +0.64%)
Open: 2,851.00   High: 2,882.90   Low: 2,846.50
52W: 2,221.05 - 3,025.00
```

### Move Board

```text
tickertrail> move 1mo

Directional Move (1MO) - Watchlist swing
Symbol               Green/Red   Move Dots
TCS.NS                 14/8      ●●●●●●○●●○●●●○●●○●●○●●
INFY.NS                12/10     ●●○●○●○●●○●○●●○●○●●○●○
RELIANCE.NS            10/12     ○●○●○○●○●○○●○●○○●○●○○●
```

### Trend Board

```text
tickertrail> trend

Trend (Current) - Watchlist swing
Symbol               Score
TCS.NS               3.0/4
INFY.NS              2.0/4
RELIANCE.NS          1.0/4
```

### Relative Return

```text
tickertrail> rr 3mo

Relative Return (3MO) - Watchlist swing vs NIFTY 50 (^NSEI)
Symbol               Return      Bench     RelRet
TCS.NS               +8.14%     +3.72%    +4.42%
INFY.NS              +5.09%     +3.72%    +1.37%
RELIANCE.NS          +1.88%     +3.72%    -1.84%
```

### Correlation Summary

```text
tickertrail> corr 6mo

Correlation (6MO) - Watchlist swing
Top Positive:
TCS.NS <-> INFY.NS         +0.82

Top Negative:
RELIANCE.NS <-> INFY.NS    -0.21

Near Zero (Diversifiers):
RELIANCE.NS <-> TCS.NS     +0.04
```

### Snapshot

```text
tickertrail> snap

Snap: NIFTY IT (10 constituents)
Symbol                    Price             Change              Range
MPHASIS.NS             2,296.50    +35.00 (+1.55%)     [──●─────────]
HCLTECH.NS             1,389.10    +15.60 (+1.14%)     [───●────────]
OFSS.NS                6,932.00    +75.50 (+1.10%)     [───────●────]
INFY.NS                1,300.10    +11.00 (+0.85%)     [──●─────────]
WIPRO.NS                 200.96     -0.12 (-0.06%)     [───●────────]
...
Snap fetch passes used: 1
```

### Swing Chart (`c`)

```text
tickertrail> c 6mo

RELIANCE.NS vs NIFTY 50 | 6MO | 1d
 122 |                              *  *
 116 |                         *  *      *
 110 |                    *  *            *
 104 |               *  *                  *
  98 |          *  *                        *
  92 |     *  *                              *
      -----------------------------------------
       Jan      Feb      Mar      Apr      May
```

### Intraday Chart (`cc`)

```text
tickertrail> cc 5m

RELIANCE.NS | 1D | 5m
 2890 |                 * *
 2884 |              * *   * *
 2878 |           * *         *
 2872 |        * *             *
 2866 |     * *                 *
       ----------------------------
        10:00 11:00 12:00 13:00
```

### Swing Table (`t`)

```text
tickertrail> t 1y

RELIANCE.NS vs NIFTY 50 | 1Y | 1wk
Date         StockIdx   BenchIdx   Delta
2025-03-01    100.00     100.00    +0.00
2025-06-01    108.42     104.15    +4.27
2025-09-01    112.36     109.02    +3.34
2025-12-01    118.51     113.27    +5.24
2026-03-01    121.08     116.44    +4.64
```

### Intraday Table (`tt`)

```text
tickertrail> tt 15m

RELIANCE.NS vs NIFTY 50 | 1D | 15m
Time         StockIdx   BenchIdx   Delta
09:30         100.00     100.00    +0.00
10:30         100.28      99.92    +0.36
11:30         100.11      99.88    +0.23
12:30         100.45      99.97    +0.48
13:30         100.62     100.03    +0.59
```

### Multi-Symbol Compare (`cmp`)

```text
tickertrail> cmp tcs infy reliance 1y w

Compare (rebased=100) | 1Y | 1wk
Date         TCS.NS    INFY.NS   RELIANCE.NS
2025-03-01   100.00    100.00      100.00
2025-06-01   106.21    104.88      108.42
2025-09-01   109.74    107.01      112.36
2025-12-01   113.56    109.92      118.51
2026-03-01   117.08    112.44      121.08
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
