"""Command-line interface entry point for QED."""

import argparse
import asyncio
import sys
from pathlib import Path

from qed import __version__
from qed.engine.run import run_problem
from qed.trust.certificate import make_certificate, verify_certificate

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


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

    # 1. run
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

    # 2. verify
    verify_parser = subparsers.add_parser(
        "verify", help="Verify a mathematical discovery certificate"
    )
    verify_parser.add_argument(
        "certificate",
        type=str,
        help="Path to certificate JSON file",
    )

    # 3. make-cert
    make_cert_parser = subparsers.add_parser(
        "make-cert", help="Create a verified certificate from a run's best program"
    )
    make_cert_parser.add_argument(
        "--run",
        "--run-id",
        dest="run_id",
        type=str,
        default=None,
        help="Identifier or directory of the completed run",
    )
    make_cert_parser.add_argument(
        "--construction",
        type=str,
        default=None,
        help="Path to hand-built construction JSON file for demonstration claims",
    )
    make_cert_parser.add_argument(
        "--claim-type",
        type=str,
        required=True,
        choices=["demonstration", "reproduction", "record"],
        help="Classification of the claim",
    )
    make_cert_parser.add_argument(
        "--best-known",
        "--best-known-value",
        dest="best_known_value",
        type=str,
        default=None,
        help="Exact string of best known value (e.g. '2.635' or '38/15')",
    )
    make_cert_parser.add_argument(
        "--source-url",
        "--best-known-url",
        dest="best_known_url",
        type=str,
        default=None,
        help="Literature or baseline source URL for best known value",
    )
    make_cert_parser.add_argument(
        "--best-known-date",
        type=str,
        default=None,
        help="Retrieval date for best known value (YYYY-MM-DD)",
    )
    make_cert_parser.add_argument(
        "--out",
        type=str,
        required=True,
        help="Destination path to write verified certificate JSON",
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


def handle_verify_command(args: argparse.Namespace) -> int:
    """Handle execution of the verify subcommand."""
    try:
        passed, check_lines, score_p_q, score_dec = verify_certificate(args.certificate)
        for line in check_lines:
            print(line)
        if passed:
            print("PASS")
            print(f"Score (exact): {score_p_q}")
            print(f"Score (decimal): {score_dec}")
            return 0
        print("FAIL")
        return 1
    except Exception as exc:
        print(f"Execution: FAILED: {exc}")
        print("FAIL")
        return 1


def handle_make_cert_command(args: argparse.Namespace) -> int:
    """Handle execution of the make-cert subcommand."""
    try:
        # Check if run_id is a path on disk or an ID
        run_dir: Path | None = None
        run_id: str | None = getattr(args, "run_id", None)
        if run_id and Path(run_id).exists():
            run_dir = Path(run_id)
            run_id = run_dir.name

        cert_data = make_certificate(
            run_id=run_id,
            run_dir=run_dir,
            construction_path=getattr(args, "construction", None),
            claim_type=args.claim_type,
            out_path=args.out,
            best_known_value=getattr(args, "best_known_value", None),
            best_known_url=getattr(args, "best_known_url", None),
            best_known_date=getattr(args, "best_known_date", None),
        )
        score = cert_data["claimed_score"]
        print(f"Certificate issued to {args.out} with exact score {score}")
        return 0
    except Exception as exc:
        print(f"make-cert FAILED: {exc}")
        return 1


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
    if args.command == "verify":
        return handle_verify_command(args)
    if args.command == "make-cert":
        return handle_make_cert_command(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
