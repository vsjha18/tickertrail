"""Run unittest discovery with one-line PASS/FAIL output per test.

This runner intentionally suppresses test stdout/stderr so `make test`
shows only deterministic per-test status lines.
"""

from __future__ import annotations

import contextlib
import io
import sys
import unittest
from collections.abc import Iterator


def _iter_cases(suite: unittest.TestSuite) -> Iterator[unittest.TestCase]:
    """Yield individual test cases from a potentially nested test suite."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _iter_cases(item)
            continue
        yield item


def main() -> int:
    """Execute discovered tests and print only '<test_id> PASS/FAIL' lines."""
    loader = unittest.TestLoader()
    suite = loader.discover("tests")
    failures = 0
    total = 0

    for case in _iter_cases(suite):
        total += 1
        result = unittest.TestResult()
        # Silence noisy command output from CLI rendering paths during tests.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            case.run(result)

        test_name = case.id()
        if result.wasSuccessful():
            print(f"{test_name} PASS")
        else:
            print(f"{test_name} FAIL")
            failures += 1

    passed = total - failures
    print(f"TOTAL: {total} | PASS: {passed} | FAIL: {failures}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
