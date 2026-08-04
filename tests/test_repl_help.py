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
        self.assertIn("Watchlist Commands:", text)

    def test_command_alias_and_defaults_rendering(self):
        """Resolve aliases and render entries with and without defaults."""
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            repl_help.print_help("rr", "Nd|Nmo(<12)|Ny")
            repl_help.print_help("q", "Nd|Nmo(<12)|Ny")
            repl_help.print_help("cache clear", "Nd|Nmo(<12)|Ny")
        text = out.getvalue()
        self.assertIn("Command: relret", text)
        self.assertIn("Command: quote", text)
        self.assertIn("symbol: current active symbol", text)
        self.assertIn("Command: cache clear", text)
        self.assertIn("- none", text)

    def test_unknown_topic_reports_to_stderr(self):
        """Keep unknown-topic diagnostics on stderr."""
        with patch("sys.stderr", new_callable=io.StringIO) as err:
            repl_help.print_help("not-a-command", "Nd|Nmo(<12)|Ny")
        self.assertIn("Unknown help topic", err.getvalue())


if __name__ == "__main__":
    unittest.main()
