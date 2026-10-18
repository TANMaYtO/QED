"""Command-line interface entry point for QED."""

import argparse
import asyncio
import sys

from qed import __version__
from qed.engine.run import run_problem


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

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    run_parser = subparsers.add_parser(
        "run", help="Launch evolutionary search on a problem"
    )
    run_parser.add_argument(
        "problem",
        type=str,
        help="Identifier of problem (e.g. circle_packing_n26)",
    )
    run_parser.add_argument(
        "-i",
        "--iterations",
        type=int,
        default=20,
        help="Number of evolution iterations to run",
    )
    run_parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Explicit identifier for the run",
    )

    return parser


def handle_run_command(args: argparse.Namespace) -> int:
    """Handle execution of the run subcommand."""
    summary = asyncio.run(
        run_problem(
            problem_id=args.problem,
            iterations=args.iterations,
            run_id=args.run_id,
        )
    )
    best_score: float = summary["best_fast_score"]
    wall_time: float = summary["wall_time"]
    run_id: str = summary["run_id"]
    print(
        f"Run {run_id} finished: best score = {best_score:.6f}, "
        f"wall time = {wall_time:.2f}s"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the command-line interface with supplied arguments."""
    parser = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        parser.print_help()
        return 0

    args = parser.parse_args(argv)
    if args.command == "run":
        return handle_run_command(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
