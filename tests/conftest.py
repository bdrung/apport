"""Add --maxskip parameter to pytest."""

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add --maxskip parameter to pytest."""
    parser.addoption(
        "--maxskip",
        type=int,
        default=-1,
        help="Maximum allowed skipped tests. Set to -1 to disable."
        " (default: %(default)s)",
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Check that not too many tests were skipped."""
    maxskip = session.config.getoption("--maxskip")
    if maxskip >= 0:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        assert reporter is not None
        skipped_count = len(reporter.stats.get("skipped", []))

        if skipped_count > maxskip:
            session.exitstatus = exitstatus + 2
            print(
                f"\n[ERROR] Test suite failed: {skipped_count} tests skipped"
                f" (max allowed: {maxskip})."
            )
