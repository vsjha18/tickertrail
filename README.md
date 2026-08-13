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
- Inspect stock and index F&O chains with live Upstox prices and Greeks (`chain` / `oc`)
- Build and manage persistent watchlists
- Run analytics boards (`move`, `trend`, `relret`/`rr`, `corr`)

## Code Structure

- `cli.py`: entry point, compatibility adapters, and REPL controller orchestration
- `command_parser.py`: typed, network-free command grammar shared by CLI entry points
- `repl_help.py`: data-driven REPL overview, topic, command, and alias help
- `upstox_service.py`: Upstox token persistence, contract-calendar resolution, API normalization, and ATM-window selection
- `index_config.py`: canonical index aliases, board membership, fetch mappings, and prompt labels
- `price_history.py` / `snapshot_service.py`: reusable market-data services with injected network callbacks
- `views.py` / `quote_tools.py`: presentation and quote analytics
- `timeframe.py` / `market_hours.py`: shared period and market-session policy

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

### 1) Stock mode (`tt>stock>infy>`)

- Entered by typing a stock symbol (example: `infy`).
- `quote`, `c`, `cc`, `t`, `tt` run on the active symbol.
- `move`, `trend`, `relret` run on the active symbol.
- `corr` needs at least two symbols, so use `corr on <code1> <code2> ...`.

### 2) Index mode (`tt>index>bank>`)

- Entered by typing an index alias/symbol (example: `nifty`, `it`, `defence`, `^cnxit`).
- If live quote fields are partial, TickerTrail still keeps you in index mode and shows the best available values.
- `snap` shows constituents for supported indices.
- `move`, `trend`, `relret`, `corr` can be run with no arguments:
  - `move` runs over index constituents when available.
  - `trend` runs over index constituents when available.
  - `relret` runs over index constituents with an index-appropriate benchmark.
  - `corr` runs over index constituents and needs at least two valid overlapping series.
- In any Indian stock/index mode, `chain` / `oc` shows its option chain when Upstox lists F&O contracts.

### 3) Watchlist mode (`tt>watchlist>sharekhan>`)

- Entered with `watchlist open <name>`.
- Type `?` to show the commands available from the current prompt; in this mode the list is limited to watchlist operations, applicable analytics, navigation, and general commands.
- `move`, `trend`, `relret`, `corr` with no arguments run on symbols in that watchlist.
- `snap` shows the current watchlist snapshot.

### 4) Configuration mode (`tt>config>`)

- Entered with `config` from the main prompt.
- Type `?` for commands valid at this prompt or `help token` for token-command details.
- `token add upstox <token>` immediately saves the inline analytics token.
- `end` or `exit` returns directly to `tt>`.
- From a normal prompt, `show token` or `show token upstox` reports configuration status without printing the token value.

### 5) Explicit override mode (`on ...`)

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
- `t` default period: `6mo` (default bin auto-selected from period: `<=7d -> 1d`, `<=1mo -> 1wk`, `>1mo and <=3y -> 1mo`, `>3y -> 1y`)
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
tt> quote

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
tt> move on infy tcs reliance 1mo

Moves (1MO) - Explicit symbols
Symbol           Up Days      Dots
INFY.NS          18/30        oooooooooooooooooooooooooooooo
TCS.NS           16/30        oooooooooooooooooooooooooooooo
RELIANCE.NS      14/30        oooooooooooooooooooooooooooooo
```

### Trend Board

```text
tt> trend on infy tcs reliance

Trend (Current) - Explicit symbols
Symbol           Trend Score
INFY.NS          5.0/5.0
TCS.NS           5.0/5.0
RELIANCE.NS      5.0/5.0
```

### Relative Return

```text
tt> rr on infy tcs reliance vs nifty 1mo

Relative Return (1MO) - Explicit symbols vs NIFTY 50 (^NSEI)
Symbol               Return      Bench     RelRet
INFY.NS             +15.13%    +12.06%     +3.07%
RELIANCE.NS         +13.24%    +12.06%     +1.18%
TCS.NS              +10.86%    +12.06%     -1.20%
```

### Correlation Summary

```text
tt> corr on infy tcs reliance 1mo

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
tt> snap

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

Grouped snapshot views (`index`, `snap`, and watchlist snapshots) partition symbols by their exchange session. Open markets use two sessions of batched `download` minute bars: the prior minute session supplies the previous close, while the latest session supplies the live price and day range; daily history is requested only for symbols whose minute data is incomplete. Large universes are split into sequential batches of at most 20 symbols with yfinance download threading disabled, preventing request bursts that commonly produce partial frames. Missing symbols are retried in later batch passes after short backoffs, with no cached data in that live workflow. Closed markets first request daily-close batches. If Yahoo's daily candle is behind the latest completed session, the final minute session replaces it before the result is persisted under that exchange-session date. Repeated post-market snapshots therefore reuse accurate EOD cache entries and render `EOD data as of DD-MM-YY` rather than stale intraday data as live.
Analytics that depend on the latest daily point, such as `move`, `trend`, `relret`, and `corr`, overlay the current batched minute-market price during market hours and fall back to cached/EOD history when the market is closed.
For supported indices that need a Yahoo-specific fetch code, TickerTrail keeps one explicit fetch-symbol mapping per index instead of probing multiple alternates at runtime.
If the index board's grouped batch fetch comes back empty after an idle session, TickerTrail falls back to direct per-index quote fields for those rows instead of showing a board full of `n/a`.
Grouped snapshot commands keep freshness inline with the title or section header, and daily analytics commands print a live-overlay freshness line only when the latest daily point has been updated from minute-bar data.

### Swing Chart (`c`)

```text
tt> c 6mo

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
Last: 212.71
Move: +68.71 (+47.72%) | From: 03-09-25 -> 01-03-26
```

### Intraday Chart (`cc`)

```text
tt> cc 5m

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
tt> t 1y

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
tt> tt 15m

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

Tables are unsampled: row spacing always matches the header bin (for example `bin=5m` means 5-minute rows, `bin=1wk` means weekly rows).

### Multi-Symbol Compare (`cmp`)

```text
tt> cmp tcs infy reliance 1y w

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

- `?`: show a concise command list for the current prompt context (`tt`, stock, index, or watchlist)
- `h` / `help [topic|command]`: help system
- `quote` / `q`: show active symbol/index quote
- `cache`: show today's history cache summary
- `cache clear`: clear today's history cache
- `reload` / `r`: refresh quote and replay last chart/table
- `cls` / `clear`: clear terminal
- Press `Ctrl+C` during an in-progress command to cancel that command and return to the prompt
- Press `Ctrl+C` on an empty prompt to exit the REPL
- `quit` / `exit`: leave REPL
- `!<shell-cmd>`: run shell command

## Symbol and Index Commands

- `<symbol>`: switch active symbol and print quote
- `code <query>`: fuzzy ticker lookup from local universe
- `news <code>`: recent headlines for a symbol/index alias
- `index`: index board
- `index list`: supported index catalog
- `snap`: snapshot for active index/watchlist context

## Stock and Index Option Chains (Upstox)

Configure the Upstox analytics token once from the REPL:

```text
tt> config
tt>config> token add upstox <token>
Upstox analytics token saved to .../.upstox_analytics_token.
tt>config> end
tt> show token
Upstox analytics token: configured
Token file: .../.upstox_analytics_token
```

Then enter any Indian F&O stock/index context and request its chain:

```text
tt> nifty
tt>index>nifty> chain
tt>index>nifty> chain next
tt>index>nifty> chain far strikes 15
tt>index>nifty> chain month
tt>index>nifty> chain expiry 2026-08-27 strikes 10
tt> reliance
tt>stock>reliance> chain next
tt>stock>reliance> chain month strikes 15
```

The bare form uses the active stock or index. From any prompt, the explicit form accepts a stock ticker or index alias, for example `chain reliance next`, `chain bank month`, or `chain sensex`. `oc` is an alias for `chain`. TickerTrail resolves an exact NSE/BSE stock or index through Upstox and then checks its current option contracts; a cash-only symbol fails cleanly instead of showing an unrelated fuzzy match.

Expiry qualifiers:

- `near`: first listed future expiry and the default
- `next`: second listed future expiry
- `far`: third listed future expiry
- `month`: first listed non-weekly expiry
- `expiry YYYY-MM-DD`: exact expiry date

For every qualifier—including an exact date—TickerTrail first reads the selected underlying's current Upstox contract calendar. This both verifies that the stock/index is an F&O underlying and keeps expiry selection correct across weekly indices, monthly-only indices, and monthly stock options. An exact date must be present in that contract calendar.

The optional `strikes <1-25>` modifier controls how many strikes are shown on each side of ATM; the default is 10. The chain is ordered from higher strikes at the top to lower strikes at the bottom. Calls are on the left, puts on the right, and the strike spine is centered and bold. Headers and the complete ATM row are bold. Each call/put half is independently colored by its daily move, and LTP shows that move in brackets. The compact table shows LTP, Delta immediately beside it, Theta, volume, and OI; IV, Gamma, and Vega are omitted so the table fits within 120 columns for typical values. The heading shows the selected underlying's current value and its absolute and percentage move.

Use `chain ?`, `oc ?`, or `help chain` for situational help. Upstox access is read-only in this feature and never falls back to another data source. HTTP requests identify TickerTrail explicitly so Upstox's gateway does not reject Python's default client signature; API, authentication, and gateway errors remain distinct in CLI output.

## Charts and Tables

- Swing chart: `c [<benchmark>] [<period>]`
- Swing chart (dash override): `c [<benchmark>] - <period|agg> [agg]`
- Intraday chart: `cc [<benchmark>] [<1m|5m|15m|30m|1hr>]`
- Swing table: `t [<benchmark>] [<period>]`
- Swing table (dash override): `t [<benchmark>] - <period|agg> [agg]`
- Intraday table: `tt [<benchmark>] [<1m|5m|15m|30m|1hr>]`
- Multi-symbol compare: `cmp <symbol1> <symbol2> [symbolN ...] [period [agg]]`

Period and aggregation tokens:
- Period units: `d`, `w`, `mo`, `y`, `max`
- Aggregation units: `m`, `d`, `w`, `mo`, `y`
- `m` means minute, `mo` means month

Override examples (`t/c/cc/tt`):
- Active symbol stays the same; first positional token is benchmark override.
- Change only bin size: `t - w`, `c - mo`, `cc - 15m`, `tt - 30m`
- Change benchmark + bin size: `t bank - w`, `c nifty - mo`, `cc bank - 15m`, `tt bank - 30m`
- Change period + bin size (swing only): `t - 1y mo`, `c - 2y w`
- Yearly binning example: `t - 5y y`

## Watchlists

Top-level:
- `watchlist create <name>`
- `watchlist list`
- `watchlist open <name>`
- `watchlist delete <name>`
- `watchlist merge <wl1> <wl2> <target>`
- `watchlist` (exit watchlist mode)
- If the watchlist database cannot be read temporarily, the app reports a database read error instead of incorrectly saying the watchlist does not exist.

Inside watchlist mode (`tt>watchlist>sharekhan>`):
- `add <code...>`
  - Validates against the bundled local NSE symbol universe without network calls, including the curated ETF/fund supplement shipped with the app.
- `delete <code...>`
- `delete all`: remove every symbol from the active watchlist after typing `yes` at the confirmation prompt
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
- Upstox analytics token: `.upstox_analytics_token` (repository-local, mode `0600`, and ignored by Git)

## Notes

- Some symbols/intervals can return partial market data.
- Intraday availability can vary by symbol and market session.
- `cc 1m` and `cc 5m` can differ slightly because of timing and data availability.
- Quote `Day Range` and `52W Range` are rendered as terminal-friendly bars.
- You can also start directly with a symbol, for example:

```bash
uv run tickertrail RELIANCE
```
