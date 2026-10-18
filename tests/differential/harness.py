"""Differential testing harness between verifier_exact and check_circle_packing.

Executes both verifiers across generated cases, validates exit code, first-line
class, and informational violation parity, and runs subprocess CLI validation
on a sample of cases.
"""

from __future__ import annotations

import asyncio
import random
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from qed.problems.circle_packing_n26.independent import check_circle_packing
from qed.problems.circle_packing_n26.verifier_exact import (
    format_verification_output,
    parse_construction_json,
    verify_packing_exact,
)
from tests.differential.generators import RNG_SEED


@dataclass
class Disagreement:
    """Records a single differential discrepancy."""

    case_id: str
    raw_snippet: str
    exit_exact: int
    exit_indep: int
    out_exact: list[str]
    out_indep: list[str]
    discrepancy_type: str
    details: str


@dataclass
class DifferentialReport:
    """Summary of differential test run across all generators."""

    total_cases: int
    case_counts: dict[str, int]
    disagreements: list[Disagreement] = field(default_factory=list)
    soft_disagreements: list[Disagreement] = field(default_factory=list)
    cli_sample_verified: int = 0
    cli_sample_errors: list[str] = field(default_factory=list)


def run_verifier_exact_bytes(raw_bytes: bytes) -> tuple[int, list[str]]:
    """Execute verifier_exact in-memory on raw byte content."""
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return 1, ["INVALID format_error: UTF-8 byte-order mark (BOM) is not allowed"]
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return 1, [
            f"INVALID format_error: Invalid UTF-8 encoding in construction file: {exc}"
        ]

    try:
        centers, radii = parse_construction_json(text)
        result = verify_packing_exact(centers, radii)
        out_lines = format_verification_output(result).splitlines()
        return (0 if result.ok else 1), out_lines
    except (ValueError, TypeError) as exc:
        return 1, [f"INVALID format_error: {exc}"]


def run_independent_bytes(raw_bytes: bytes) -> tuple[int, list[str]]:
    """Execute check_circle_packing in-memory on raw byte content."""
    try:
        data = check_circle_packing.parse_and_validate_json(raw_bytes)
        is_valid, score_str, violations = check_circle_packing.evaluate_construction(
            data
        )
    except check_circle_packing.FormatError as exc:
        return 1, [f"INVALID format_error: {exc}"]

    if is_valid:
        return 0, [f"VALID {score_str}"]

    output_lines = ["INVALID"]
    output_lines.extend(violations)
    return 1, output_lines


def compare_outputs(
    case_id: str,
    raw_bytes: bytes,
    res_exact: tuple[int, list[str]],
    res_indep: tuple[int, list[str]],
) -> tuple[Disagreement | None, Disagreement | None]:
    """Compare exit codes, first-line class, and soft violation lines."""
    code_exact, lines_exact = res_exact
    code_indep, lines_indep = res_indep

    snippet = (
        repr(raw_bytes[:100])
        if len(raw_bytes) <= 100
        else f"{repr(raw_bytes[:100])}..."
    )
    hard_disagree: Disagreement | None = None
    soft_disagree: Disagreement | None = None

    # 1. Exit code parity check
    if code_exact != code_indep:
        hard_disagree = Disagreement(
            case_id=case_id,
            raw_snippet=snippet,
            exit_exact=code_exact,
            exit_indep=code_indep,
            out_exact=lines_exact,
            out_indep=lines_indep,
            discrepancy_type="exit_code_mismatch",
            details=(
                f"Exact verifier returned {code_exact}, "
                f"independent returned {code_indep}"
            ),
        )
        return hard_disagree, None

    # 2. First-line class equivalence check
    l1_exact = lines_exact[0] if lines_exact else ""
    l1_indep = lines_indep[0] if lines_indep else ""

    if l1_exact.startswith("VALID"):
        if not l1_indep.startswith("VALID"):
            hard_disagree = Disagreement(
                case_id=case_id,
                raw_snippet=snippet,
                exit_exact=code_exact,
                exit_indep=code_indep,
                out_exact=lines_exact,
                out_indep=lines_indep,
                discrepancy_type="valid_class_mismatch",
                details=f"Exact: {l1_exact!r}, Independent: {l1_indep!r}",
            )
        elif l1_exact != l1_indep:
            hard_disagree = Disagreement(
                case_id=case_id,
                raw_snippet=snippet,
                exit_exact=code_exact,
                exit_indep=code_indep,
                out_exact=lines_exact,
                out_indep=lines_indep,
                discrepancy_type="score_value_mismatch",
                details=f"Score string mismatch: {l1_exact!r} vs {l1_indep!r}",
            )
    elif l1_exact == "INVALID":
        if l1_indep != "INVALID":
            hard_disagree = Disagreement(
                case_id=case_id,
                raw_snippet=snippet,
                exit_exact=code_exact,
                exit_indep=code_indep,
                out_exact=lines_exact,
                out_indep=lines_indep,
                discrepancy_type="invalid_geometry_mismatch",
                details=f"Exact: {l1_exact!r}, Independent: {l1_indep!r}",
            )
    elif l1_exact.startswith("INVALID format_error"):
        if not l1_indep.startswith("INVALID format_error"):
            hard_disagree = Disagreement(
                case_id=case_id,
                raw_snippet=snippet,
                exit_exact=code_exact,
                exit_indep=code_indep,
                out_exact=lines_exact,
                out_indep=lines_indep,
                discrepancy_type="format_error_mismatch",
                details=f"Exact: {l1_exact!r}, Independent: {l1_indep!r}",
            )
    else:
        hard_disagree = Disagreement(
            case_id=case_id,
            raw_snippet=snippet,
            exit_exact=code_exact,
            exit_indep=code_indep,
            out_exact=lines_exact,
            out_indep=lines_indep,
            discrepancy_type="unknown_line1_class",
            details=f"Unrecognized line 1 from exact verifier: {l1_exact!r}",
        )

    # 3. Soft check: set of informational violation lines
    if hard_disagree is None and l1_exact == "INVALID" and l1_indep == "INVALID":
        set_exact = set(lines_exact[1:])
        set_indep = set(lines_indep[1:])
        if set_exact != set_indep:
            soft_disagree = Disagreement(
                case_id=case_id,
                raw_snippet=snippet,
                exit_exact=code_exact,
                exit_indep=code_indep,
                out_exact=lines_exact,
                out_indep=lines_indep,
                discrepancy_type="violation_set_difference",
                details=(
                    f"Violation lines differ: diff_exact={set_exact - set_indep}, "
                    f"diff_indep={set_indep - set_exact}"
                ),
            )

    return hard_disagree, soft_disagree


async def run_cli_subprocess_check(
    raw_bytes: bytes,
) -> tuple[int, list[str], int, list[str]]:
    """Run both checkers via subprocess CLI on a temporary file."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp.write(raw_bytes)
        tmp_path = tmp.name

    try:
        # 1. Exact verifier CLI
        proc_exact = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "qed.problems.circle_packing_n26.verifier_exact",
            tmp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_e, _ = await proc_exact.communicate()
        code_e = proc_exact.returncode or 0
        lines_e = stdout_e.decode("utf-8", errors="replace").splitlines()

        # 2. Independent checker CLI
        script_indep = str(Path(check_circle_packing.__file__).resolve())
        proc_indep = await asyncio.create_subprocess_exec(
            sys.executable,
            script_indep,
            tmp_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_i, _ = await proc_indep.communicate()
        code_i = proc_indep.returncode or 0
        lines_i = stdout_i.decode("utf-8", errors="replace").splitlines()

        return code_e, lines_e, code_i, lines_i
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def run_differential_harness(
    cases: list[tuple[str, bytes]],
    counts: dict[str, int],
    cli_sample_size: int = 300,
) -> DifferentialReport:
    """Execute differential comparison over all cases and sample CLI verification."""
    report = DifferentialReport(
        total_cases=len(cases),
        case_counts=counts,
    )

    for case_id, raw_bytes in cases:
        res_exact = run_verifier_exact_bytes(raw_bytes)
        res_indep = run_independent_bytes(raw_bytes)

        hard, soft = compare_outputs(case_id, raw_bytes, res_exact, res_indep)
        if hard is not None:
            report.disagreements.append(hard)
        if soft is not None:
            report.soft_disagreements.append(soft)

    # CLI subprocess parity on random sample of cases
    rng = random.Random(RNG_SEED + 99)
    sample_indices = rng.sample(range(len(cases)), min(cli_sample_size, len(cases)))

    async def run_cli_samples() -> None:
        sem = asyncio.Semaphore(10)

        async def check_one(idx: int) -> None:
            cid, raw_data = cases[idx]
            async with sem:
                ce, le, ci, li = await run_cli_subprocess_check(raw_data)
            if ce != ci:
                report.cli_sample_errors.append(
                    f"CLI exit mismatch on {cid}: exact={ce}, indep={ci}"
                )
            l1_e = le[0] if le else ""
            l1_i = li[0] if li else ""
            if l1_e.startswith("VALID") and (
                not l1_i.startswith("VALID") or l1_e != l1_i
            ):
                report.cli_sample_errors.append(
                    f"CLI score mismatch on {cid}: {l1_e} vs {l1_i}"
                )
            elif l1_e == "INVALID" and l1_i != "INVALID":
                report.cli_sample_errors.append(
                    f"CLI invalid mismatch on {cid}: {l1_e} vs {l1_i}"
                )
            elif l1_e.startswith("INVALID format_error") and not l1_i.startswith(
                "INVALID format_error"
            ):
                report.cli_sample_errors.append(
                    f"CLI format_error mismatch on {cid}: {l1_e} vs {l1_i}"
                )
            report.cli_sample_verified += 1

        await asyncio.gather(*(check_one(idx) for idx in sample_indices))

    asyncio.run(run_cli_samples())
    return report
