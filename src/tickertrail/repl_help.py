from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class HelpEntry:
    """Describe one command-help page rendered by the REPL."""

    command: str
    aliases: tuple[str, ...] = ()
    usage: tuple[str, ...] = ()
    details: tuple[str, ...] = ()
    defaults: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()


_COMMAND_ALIASES: dict[str, str] = {
    "?": "?",
    "h": "help",
    "help": "help",
    "q": "quote",
    "quote": "quote",
    "quit": "quit",
    "exit": "quit",
    "cls": "clear",
    "clear": "clear",
    "cache": "cache",
    "cache clear": "cache clear",
    "reload": "reload",
    "r": "reload",
    "refresh": "reload",
    "!": "shell",
    "!<shell-cmd>": "shell",
    "code": "code",
    "news": "news",
    "index": "index",
    "index list": "index list",
    "snap": "snap",
    "move": "move",
    "moves": "move",
    "trend": "trend",
    "trends": "trend",
    "relret": "relret",
    "rr": "relret",
    "corr": "corr",
    "cmp": "cmp",
    "chart": "chart",
    "chart swing": "chart swing",
    "chart intra": "chart intra",
    "c": "c",
    "cc": "cc",
    "table": "table",
    "table swing": "table swing",
    "table intra": "table intra",
    "t": "t",
    "tt": "tt",
    "watchlist": "watchlist",
    "watchlist create": "watchlist create",
    "watchlist list": "watchlist list",
    "watchlist open": "watchlist open",
    "watchlist delete": "watchlist delete",
    "watchlist merge": "watchlist merge",
    "wl": "watchlist",
    "wl create": "watchlist create",
    "wl list": "watchlist list",
    "wl open": "watchlist open",
    "wl delete": "watchlist delete",
    "wl merge": "watchlist merge",
    "add": "add",
    "delete": "delete",
    "delete all": "delete",
    "list": "list",
    "ll": "list",
    "<period>": "<period>",
    "<symbol>": "<symbol>",
}


_OVERVIEW_LINES = (
    "",
    "Tickertrail Help",
    "===============",
    "Use `help <command>` for command-level details.",
    "Use `help core|chart|table|watchlist|index` for category summaries.",
    "",
    "Core Commands:",
    "  ?                           Show commands for the current prompt",
    "  h | help [topic|command]    Show organized help",
    "  quote | q                   Show current symbol/index quote",
    "  news <code>                 Show recent Yahoo headlines",
    "  quit | exit                 Exit",
    "  cls | clear                 Clear terminal",
    "  reload | r                  Refresh quote + replay last chart/table",
    "  !<shell-cmd>                Run shell command",
    "  cache                       Show today's persisted history cache summary",
    "  cache clear                 Clear today's persisted history cache",
    "",
    "Analytics:",
    "  move [period]               Directional move-dot board (alias: moves)",
    "  trend                       Current trend-score board (alias: trends)",
    "  relret [period]             Relative-return ranking (alias: rr)",
    "  corr [period]               Correlation summary",
    "  cmp <symbols...> [period [agg]]   Rebased compare table",
    "",
    "Market + Discovery:",
    "  <symbol>                    Switch active symbol + quote",
    "  code <query>                Fuzzy ticker lookup",
    "  news <code>                 Recent Yahoo symbol headlines",
    "  index | index list          Index board and symbol catalog",
    "  snap                        Active index/watchlist snapshot",
    "",
    "Charts + Tables:",
    "  chart swing ... | c ...     Swing chart",
    "  chart intra ... | cc ...    Intraday chart",
    "  table swing ... | t ...     Swing rebased table",
    "  table intra ... | tt ...    Intraday rebased table",
    "  <period>                    Shortcut for swing chart period",
    "",
    "Watchlists:",
    "  watchlist create|list|open|delete|merge ...",
    "  wl ...                      Alias namespace",
    "  add|delete|list|ll          Watchlist mode symbol operations",
    "",
    "Quick Start Examples:",
    "  help move",
    "  help watchlist open",
    "  news infy",
    "  chart swing nifty 3mo w",
    "  table intra nifty 15m",
    "  move 1mo",
    "  trend",
    "  relret 3mo",
    "  corr",
    "  watchlist create swing",
    "  watchlist open swing",
    "  add tcs infy reliance",
    "  snap",
    "",
)


_STAGE_HELP_LINES: dict[str, tuple[str, ...]] = {
    "base": (
        "  <symbol>                    Open a stock or index",
        "  watchlist open <name>       Open a watchlist",
        "  watchlist create|list|delete|merge ...",
        "  index | index list          Show indices",
        "  code <query> | news <code>  Find a ticker or show news",
        "  cmp <codes...> [period [agg]]",
    ),
    "stock": (
        "  quote | q                   Refresh the active quote",
        "  c | cc | t | tt ...         Show charts or tables",
        "  <period>                    Show a swing chart",
        "  move | trend | relret ...   Analyze the active symbol",
        "  <symbol>                    Switch stock or index",
        "  watchlist open <name>       Open a watchlist",
    ),
    "index": (
        "  quote | q | snap            Refresh or show constituents",
        "  move | trend | relret | corr [period]",
        "  c | cc | t | tt ...         Show charts or tables",
        "  <period>                    Show a swing chart",
        "  <symbol>                    Switch stock or index",
        "  watchlist open <name>       Open a watchlist",
    ),
    "watchlist": (
        "  add <codes...>              Add symbols",
        "  delete <codes...> | delete all",
        "  list | ll                   List symbols",
        "  snap                        Show watchlist snapshot",
        "  move [period] | trend       Analyze watchlist symbols",
        "  relret | rr [period]        Rank relative returns",
        "  corr [period]               Show correlations",
        "  <symbol>                    Switch to stock/index mode",
        "  watchlist                   Exit watchlist mode",
        "  watchlist create|list|open|delete|merge ...",
    ),
}


_STAGE_HELP_COMMON_LINES = (
    "  ?                           Show this prompt-specific list",
    "  h | help [topic|command]    Show full or detailed help",
    "  code <query> | news <code>  Find a ticker or show news",
    "  cmp <codes...> [period [agg]]",
    "  index | index list          Show indices",
    "  cache | cache clear         Inspect or clear history cache",
    "  cls | clear | !<shell-cmd>  Terminal utilities",
    "  quit | exit                 Exit TickerTrail",
)


_TOPIC_SUMMARIES: dict[str, tuple[str, ...]] = {
    "core": (
        "",
        "Core Commands:",
        "  h | help [topic|command]",
        "  quote | q",
        "  quit | exit",
        "  cls | clear",
        "  reload | r",
        "  !<shell-cmd>",
        "  cache | cache clear",
        "  code <query>",
        "  news <code>",
        "  cmp <symbols...> [period [agg]]",
        "  <period> | <symbol>",
        "",
        "Examples:",
        "  help relret",
        "  code national thermal",
        "  news infy",
        "  cmp nifty goldbees hdfcbank 1y w",
        "",
    ),
    "index": (
        "",
        "Index Commands:",
        "  index | index list | snap",
        "  move [period] | trend | relret [period] | corr [period]",
        "",
        "Examples:",
        "  index",
        "  index list",
        "  nifty",
        "  move 1mo",
        "",
    ),
    "chart": (
        "",
        "Chart Commands:",
        "  chart swing [<benchmark>] [<period>]",
        "  chart swing [<benchmark>] - <period|agg> [agg]",
        "  chart intra [<benchmark>] [<1m|5m|15m|30m|1hr>]",
        "  chart intra [<benchmark>] - <1m|5m|15m|30m|1hr>",
        "  c ... | cc ...",
        "",
        "Examples:",
        "  help c",
        "  chart swing nifty 6mo",
        "  c nifty - 2y mo",
        "  cc banknifty 5m",
        "",
    ),
    "table": (
        "",
        "Table Commands:",
        "  table swing [<benchmark>] [<period>]",
        "  table swing [<benchmark>] - <period|agg> [agg]",
        "  table intra [<benchmark>] [<1m|5m|15m|30m|1hr>]",
        "  table intra [<benchmark>] - <1m|5m|15m|30m|1hr>",
        "  t ... | tt ...",
        "",
        "Examples:",
        "  help tt",
        "  table swing nifty - 2y mo",
        "  t nifty",
        "  tt 15m",
        "",
    ),
    "watchlist": (
        "",
        "Watchlist Commands:",
        "  watchlist create <name> | wl create <name>",
        "  watchlist list | wl list",
        "  watchlist open <name> | wl open <name>",
        "  watchlist delete <name> | wl delete <name>",
        "  watchlist merge <wl1> <wl2> <target> | wl merge ...",
        "  watchlist <name> | wl <name>",
        "  watchlist   # exit mode",
        "  add <codes...> | delete <codes...> | delete all | list | ll | snap",
        "",
        "Examples:",
        "  watchlist create swing",
        "  watchlist open swing",
        "  add tcs infy reliance",
        "  move",
        "",
    ),
}


def _command_entries(period_hint: str) -> dict[str, HelpEntry]:
    """Build command-help entries that share the configured period grammar hint."""
    swing_usage = ("[<benchmark>] [<period>]", "[<benchmark>] - <period|agg> [agg]")
    intra_usage = ("[<benchmark>] [<1m|5m|15m|30m|1hr>]", "[<benchmark>] - <1m|5m|15m|30m|1hr>")
    return {
        "?": HelpEntry(
            "?",
            usage=("?",),
            details=("Show only the commands relevant to the current prompt context.",),
            examples=("?",),
        ),
        "help": HelpEntry(
            "help",
            ("h",),
            ("help", "help <topic>", "help <command>"),
            (
                "Top-level help is organized by categories and quick-start examples.",
                "Topics: core, chart, table, watchlist, index.",
                "Command-level help supports canonical commands and aliases.",
            ),
            examples=("help", "help core", "help move", "help watchlist merge"),
        ),
        "quote": HelpEntry(
            "quote",
            ("q",),
            ("quote",),
            (
                "Render quote for active stock/index symbol.",
                "Unavailable in watchlist mode; exit watchlist or switch to symbol mode first.",
            ),
            ("symbol: current active symbol",),
            ("quote", "q"),
        ),
        "quit": HelpEntry("quit", ("exit",), ("quit", "exit"), ("Exit REPL immediately.",), examples=("quit",)),
        "clear": HelpEntry("clear", ("cls",), ("clear",), ("Clear terminal screen and keep REPL session active.",), examples=("clear",)),
        "cache": HelpEntry(
            "cache",
            usage=("cache", "cache clear"),
            details=(
                "Shows today's persisted history cache summary (path, entry count, kinds, symbols).",
                "`cache clear` deletes only today's persisted history cache bucket.",
            ),
            examples=("cache", "cache clear"),
        ),
        "cache clear": HelpEntry(
            "cache clear",
            usage=("cache clear",),
            details=("Clears only today's persisted history cache bucket.",),
            examples=("cache clear",),
        ),
        "reload": HelpEntry(
            "reload",
            ("r", "refresh"),
            ("reload",),
            ("Refresh active quote and replay last non-quote chart/table/compare view.",),
            examples=("reload", "r"),
        ),
        "shell": HelpEntry(
            "!<shell-cmd>",
            usage=("!<shell-cmd>",),
            details=("Run shell command in underlying terminal context.",),
            examples=("!pwd", "!ls -la data"),
        ),
        "code": HelpEntry(
            "code",
            usage=("code <query>",),
            details=("Fuzzy-lookup likely ticker codes using local NSE universe data.",),
            examples=("code national thermal", "code bank of baroda"),
        ),
        "news": HelpEntry(
            "news",
            usage=("news <code>",),
            details=(
                "Resolve symbol and print recent Yahoo Finance news headlines.",
                "Availability varies by symbol and region.",
            ),
            defaults=("headline limit: 5",),
            examples=("news infy", "news aapl"),
        ),
        "index": HelpEntry("index", usage=("index",), details=("Show India and global index board with quote snapshot.",), examples=("index",)),
        "index list": HelpEntry("index list", usage=("index list",), details=("Show curated index symbol catalog without live quote fetch.",), examples=("index list",)),
        "snap": HelpEntry(
            "snap",
            usage=("snap",),
            details=(
                "In watchlist mode, show the watchlist snapshot board.",
                "Otherwise, show the active index constituent snapshot.",
            ),
            examples=("watchlist open swing", "snap", "nifty", "snap"),
        ),
        "move": HelpEntry(
            "move",
            ("moves",),
            (f"move [{period_hint}]", f"move on <code1> <code2> ... [{period_hint}]"),
            (
                "Show directional dots per symbol for the active context.",
                "Use `on <codes...>` to override the active context.",
                "Rows are sorted by most green days first.",
            ),
            ("period: 1mo",),
            ("move", "moves 3mo", "move on infy tcs reliance 3mo"),
        ),
        "trend": HelpEntry(
            "trend",
            ("trends",),
            ("trend", "trend on <code1> <code2> ..."),
            ("Show current trend score per symbol.", "Rows are sorted by highest score ratio first."),
            ("arguments: none",),
            ("trend", "trend on hdfcbank icicibank kotakbank"),
        ),
        "relret": HelpEntry(
            "relret",
            ("rr",),
            (
                f"relret [{period_hint}] [vs <benchmark> [{period_hint}]]",
                f"relret on <code1> <code2> ... [{period_hint}] [vs <benchmark> [{period_hint}]]",
            ),
            (
                "Show symbol, benchmark, and relative returns.",
                "Use `on <codes...>` and `vs <benchmark>` to override context.",
                "Rows are sorted by strongest outperformance first.",
            ),
            ("period: 1mo",),
            ("relret", "rr 3mo", "relret on tcs infy hcltech 6mo vs it"),
        ),
        "corr": HelpEntry(
            "corr",
            usage=(f"corr [{period_hint}]", f"corr on <code1> <code2> ... [{period_hint}]"),
            details=("Show return-correlation summaries for at least two symbols.",),
            defaults=("period: 1mo",),
            examples=("corr", "corr 6mo", "corr on infy tcs hdfcbank 3mo"),
        ),
        "cmp": HelpEntry(
            "cmp",
            usage=("cmp <symbol1> <symbol2> ... [period [agg]]",),
            details=("Show a shared base=100 comparison table for two or more symbols.",),
            defaults=("period: 1y", "aggregation: automatic"),
            examples=("cmp nifty goldbees hdfcbank", "cmp infy tcs 3y w"),
        ),
        "chart": HelpEntry("chart", usage=("chart <swing|intra> ...",), details=("Canonical chart namespace.",), examples=("chart swing nifty 6mo", "chart intra nifty 15m")),
        "chart swing": HelpEntry("chart swing", ("c",), tuple(f"chart swing {tail}" for tail in swing_usage), ("Render the swing chart.",), examples=("chart swing", "chart swing nifty - 2y mo")),
        "chart intra": HelpEntry("chart intra", ("cc",), tuple(f"chart intra {tail}" for tail in intra_usage), ("Render the intraday chart.",), examples=("chart intra", "chart intra bank 15m")),
        "c": HelpEntry("c", ("chart swing",), tuple(f"c {tail}" for tail in swing_usage), ("Short alias for `chart swing`.",), examples=("c", "c nifty 3mo w")),
        "cc": HelpEntry("cc", ("chart intra",), tuple(f"cc {tail}" for tail in intra_usage), ("Short alias for `chart intra`.",), examples=("cc", "cc nifty 5m")),
        "table": HelpEntry("table", usage=("table <swing|intra> ...",), details=("Canonical table namespace.",), examples=("table swing nifty 6mo", "table intra nifty 15m")),
        "table swing": HelpEntry("table swing", ("t",), tuple(f"table swing {tail}" for tail in swing_usage), ("Render the swing rebased table.",), examples=("table swing", "table swing nifty - 2y mo")),
        "table intra": HelpEntry("table intra", ("tt",), tuple(f"table intra {tail}" for tail in intra_usage), ("Render the intraday rebased table.",), examples=("table intra", "table intra bank 15m")),
        "t": HelpEntry("t", ("table swing",), tuple(f"t {tail}" for tail in swing_usage), ("Short alias for `table swing`.",), examples=("t", "t nifty 3mo w")),
        "tt": HelpEntry("tt", ("table intra",), tuple(f"tt {tail}" for tail in intra_usage), ("Short alias for `table intra`.",), examples=("tt", "tt nifty 5m")),
        "watchlist": HelpEntry(
            "watchlist",
            ("wl",),
            ("watchlist", "watchlist <name>", "watchlist <create|list|open|delete|merge> ..."),
            ("Manage watchlists and enter or exit watchlist mode.",),
            examples=("watchlist list", "watchlist open swing", "watchlist"),
        ),
        "watchlist create": HelpEntry("watchlist create", ("wl create",), ("watchlist create <name>",), ("Create an empty watchlist.",), examples=("watchlist create swing",)),
        "watchlist list": HelpEntry("watchlist list", ("wl list",), ("watchlist list",), ("List saved watchlists.",), examples=("watchlist list",)),
        "watchlist open": HelpEntry("watchlist open", ("wl open",), ("watchlist open <name>",), ("Enter one saved watchlist context.",), examples=("watchlist open swing",)),
        "watchlist delete": HelpEntry("watchlist delete", ("wl delete",), ("watchlist delete <name>",), ("Delete one saved watchlist.",), examples=("watchlist delete swing",)),
        "watchlist merge": HelpEntry("watchlist merge", ("wl merge",), ("watchlist merge <wl1> <wl2> <target>",), ("Merge two watchlists into a target list without duplicates.",), examples=("watchlist merge swing core combined",)),
        "add": HelpEntry("add", usage=("add <code1> <code2> ...",), details=("Add locally validated NSE symbols in watchlist mode.",), examples=("add tcs infy reliance",)),
        "delete": HelpEntry(
            "delete",
            usage=("delete <code1> <code2> ...", "delete all"),
            details=(
                "Delete selected symbols from the active watchlist.",
                "`delete all` removes every symbol after an explicit `yes` confirmation.",
            ),
            examples=("delete tcs infy", "delete all"),
        ),
        "list": HelpEntry("list", ("ll",), ("list", "ll"), ("List symbols in the active watchlist.",), examples=("list",)),
        "<period>": HelpEntry("<period>", usage=("<period>",), details=("Render the active symbol swing chart for the given period.",), examples=("1mo", "2y")),
        "<symbol>": HelpEntry("<symbol>", usage=("<symbol>",), details=("Resolve and switch the active stock or index context.",), examples=("infy", "nifty", "aapl")),
    }


def _print_lines(lines: tuple[str, ...]) -> None:
    """Print a preformatted sequence of help lines."""
    for line in lines:
        print(line)


def _print_command_help(entry: HelpEntry) -> None:
    """Render one structured command-help entry."""
    alias_text = ", ".join(entry.aliases) if entry.aliases else "none"
    print(f"\nCommand: {entry.command}")
    print(f"Aliases: {alias_text}")
    print("Usage:")
    for line in entry.usage:
        print(f"  {line}")
    print("Details:")
    for line in entry.details:
        print(f"  - {line}")
    print("Defaults:")
    if entry.defaults:
        for line in entry.defaults:
            print(f"  - {line}")
    else:
        print("  - none")
    print("Examples:")
    for line in entry.examples:
        print(f"  {line}")
    print()


def print_stage_help(stage: str, label: str | None = None) -> None:
    """Render the commands available at the current REPL prompt stage."""
    normalized_stage = stage.strip().lower()
    stage_lines = _STAGE_HELP_LINES.get(normalized_stage, _STAGE_HELP_LINES["base"])
    display_label = (label or normalized_stage).strip()
    print(f"\nCommands available here ({display_label}):")
    for line in stage_lines:
        print(line)
    print("\nGeneral commands:")
    for line in _STAGE_HELP_COMMON_LINES:
        print(line)
    print()


def print_help(topic: str | None, period_hint: str) -> None:
    """Render REPL overview, topic, or command help for one user input."""
    normalized = " ".join((topic or "").strip().lower().split())
    if not normalized:
        _print_lines(_OVERVIEW_LINES)
        return

    # Topic summaries intentionally take precedence over same-named command pages.
    topic_key = {"general": "core", "wl": "watchlist"}.get(normalized, normalized)
    summary = _TOPIC_SUMMARIES.get(topic_key)
    if summary is not None:
        _print_lines(summary)
        return

    canonical = _COMMAND_ALIASES.get(normalized)
    if canonical is None:
        print(
            f"Unknown help topic '{topic}'. Try: help move | help trend | help chart swing | help watchlist open",
            file=sys.stderr,
        )
        return
    _print_command_help(_command_entries(period_hint)[canonical])
