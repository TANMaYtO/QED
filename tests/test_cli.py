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
