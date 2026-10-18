"""Tests for the QED command-line interface."""

import pytest

from qed import __version__
from qed.cli import build_parser, main


def test_build_parser_version() -> None:
    """Verify that build_parser configures version output correctly."""
    parser = build_parser()
    assert parser.prog == "qed"


def test_cli_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify that passing --version prints the program version and exits."""
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert f"qed {__version__}" in captured.out


def test_cli_no_args_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    """Verify that running CLI with no arguments shows help without error."""
    exit_code = main([])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "usage: qed" in captured.out


def test_cli_run_subcommand(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that running qed run invokes run_problem and prints result."""
    from unittest.mock import AsyncMock, patch

    mock_summary = {
        "problem_id": "circle_packing_n26",
        "run_id": "cli_run_123",
        "best_fast_score": 0.9597,
        "wall_time": 1.25,
    }

    with patch("qed.cli.run_problem", new=AsyncMock(return_value=mock_summary)):
        exit_code = main(["run", "circle_packing_n26", "-i", "10"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Run cli_run_123 finished" in captured.out
    assert "0.9597" in captured.out
