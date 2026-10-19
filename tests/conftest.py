"""Pytest configuration and global fixtures."""

import shutil
import subprocess
from typing import Any

import pytest


def is_docker_available() -> bool:
    """Return True if docker CLI is available and docker daemon responds to info."""
    if shutil.which("docker") is None:
        return False
    try:
        proc = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        return proc.returncode == 0
    except Exception:
        return False


_DOCKER_AVAILABLE: bool = is_docker_available()


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "docker: mark test as requiring a running Docker daemon"
    )


def pytest_runtest_setup(item: pytest.Item) -> None:
    """Skip tests marked with docker when Docker daemon is not available."""
    if item.get_closest_marker("docker") and not _DOCKER_AVAILABLE:
        pytest.skip("Docker daemon is not available/running")


def pytest_terminal_summary(
    terminalreporter: Any, exitstatus: int, config: pytest.Config
) -> None:
    """Print count of skipped tests grouped by reason."""
    skipped_reports = terminalreporter.stats.get("skipped", [])
    if skipped_reports:
        reasons: dict[str, int] = {}
        for report in skipped_reports:
            reason = getattr(report, "longreprtext", "") or "unspecified"
            if "Skipped: " in reason:
                reason = reason.split("Skipped: ", 1)[1].strip()
            reasons[reason] = reasons.get(reason, 0) + 1
        terminalreporter.write_sep("-", "Skipped tests summary by reason")
        for reason, count in sorted(reasons.items()):
            terminalreporter.write_line(f"SKIPPED ({count}): {reason}")
