"""Command-line interface entry point for QED."""

import argparse
import sys

from qed import __version__


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser for the QED command line."""
    parser = argparse.ArgumentParser(
        prog="qed",
        description="QED: A discovery engine with exact verification.",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"qed {__version__}",
        help="Show program version and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command-line interface with supplied arguments."""
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        parser.print_help()
        return 0
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
