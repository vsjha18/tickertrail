import io
import unittest
from unittest.mock import patch

from tickertrail import repl_help


class ReplHelpTests(unittest.TestCase):
    def test_overview_and_topic_aliases(self):
        """Render overview and topic aliases without controller involvement."""
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            repl_help.print_help(None, "Nd|Nmo(<12)|Ny")
            repl_help.print_help("general", "Nd|Nmo(<12)|Ny")
            repl_help.print_help("wl", "Nd|Nmo(<12)|Ny")
        text = out.getvalue()
        self.assertIn("Tickertrail Help", text)
        self.assertIn("Core Commands:", text)
        self.assertIn("show token [upstox]", text)
        self.assertIn("Watchlist Commands:", text)

    def test_command_alias_and_defaults_rendering(self):
        """Resolve aliases and render entries with and without defaults."""
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            repl_help.print_help("rr", "Nd|Nmo(<12)|Ny")
            repl_help.print_help("q", "Nd|Nmo(<12)|Ny")
            repl_help.print_help("cache clear", "Nd|Nmo(<12)|Ny")
            repl_help.print_help("delete all", "Nd|Nmo(<12)|Ny")
            repl_help.print_help("oc", "Nd|Nmo(<12)|Ny")
            repl_help.print_help("token", "Nd|Nmo(<12)|Ny")
            repl_help.print_help("show", "Nd|Nmo(<12)|Ny")
        text = out.getvalue()
        self.assertIn("Command: relret", text)
        self.assertIn("Command: quote", text)
        self.assertIn("symbol: current active symbol", text)
        self.assertIn("Command: cache clear", text)
        self.assertIn("delete all", text)
        self.assertIn("Command: chain", text)
        self.assertIn("Command: token", text)
        self.assertIn("Command: show token", text)
        self.assertIn("- none", text)

    def test_unknown_topic_reports_to_stderr(self):
        """Keep unknown-topic diagnostics on stderr."""
        with patch("sys.stderr", new_callable=io.StringIO) as err:
            repl_help.print_help("not-a-command", "Nd|Nmo(<12)|Ny")
        self.assertIn("Unknown help topic", err.getvalue())

    def test_stage_help_renders_context_specific_and_common_commands(self):
        """Render concise prompt-specific command lists for each REPL stage."""
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            repl_help.print_stage_help("watchlist", "watchlist: kite")
            repl_help.print_stage_help("index", "index: nifty")
            repl_help.print_stage_help("config", "config")
            repl_help.print_stage_help("unknown")
            repl_help.print_help("?", "Nd|Nmo(<12)|Ny")
        text = out.getvalue()
        self.assertIn("Commands available here (watchlist: kite):", text)
        self.assertIn("add <codes...>", text)
        self.assertIn("delete all", text)
        self.assertIn("watchlist                   Exit watchlist mode", text)
        self.assertIn("chain | oc [qualifier]", text)
        self.assertIn("token add upstox <token>", text)
        self.assertIn("General commands:", text)
        self.assertIn("Commands available here (unknown):", text)
        self.assertIn("Command: ?", text)

        with patch("sys.stdout", new_callable=io.StringIO) as config_out:
            repl_help.print_stage_help("config", "config")
        self.assertIn("end | exit", config_out.getvalue())
        self.assertNotIn("token status", config_out.getvalue())
        self.assertNotIn("show token", config_out.getvalue())
        self.assertNotIn("cache | cache clear", config_out.getvalue())

        with patch("sys.stdout", new_callable=io.StringIO) as stock_out:
            repl_help.print_stage_help("stock", "stock: infy")
        self.assertIn("chain | oc [qualifier]", stock_out.getvalue())
        self.assertIn("chain <symbol|index>", stock_out.getvalue())
        self.assertIn("show token [upstox]", stock_out.getvalue())


if __name__ == "__main__":
    unittest.main()
