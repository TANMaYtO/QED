"""Full differential testing suite between verifier_exact and check_circle_packing.

Executes over 20,000 deterministic test cases across 6 generators (valid packings,
nudges, number string fuzzing, JSON mutations, cap boundaries, and real run data),
plus 300 subprocess CLI samples, verifying 100% agreement on exit codes and scores.
"""

from __future__ import annotations

import pytest

from tests.differential.generators import get_all_test_cases
from tests.differential.harness import run_differential_harness


@pytest.fixture(scope="module")
def differential_report():
    """Generate all cases and run the differential harness across checkers."""
    cases, counts = get_all_test_cases()
    report = run_differential_harness(cases, counts, cli_sample_size=300)
    return report


def test_generator_case_counts(differential_report) -> None:
    """Validate that all 6 generator categories meet or exceed case targets."""
    counts = differential_report.case_counts
    assert differential_report.total_cases >= 20000
    assert counts["Generator A (Exact Valid Packings)"] >= 3500
    assert counts["Generator B (Nudges)"] >= 4000
    assert counts["Generator C (Number-String Fuzz)"] >= 4500
    assert counts["Generator D (JSON-Level Mutations)"] >= 4500
    assert counts["Generator E (Cap Boundaries)"] >= 3000
    assert counts["Generator F (Real Data & Nudges)"] >= 2000


def test_zero_hard_disagreements(differential_report) -> None:
    """Validate zero exit-code, class, or score disagreements across all cases."""
    if differential_report.disagreements:
        sample_errs = [
            f"Case {d.case_id} ({d.discrepancy_type}): {d.details}"
            for d in differential_report.disagreements[:5]
        ]
        pytest.fail(
            f"Encountered {len(differential_report.disagreements)} hard "
            f"disagreements:\n" + "\n".join(sample_errs)
        )
    assert len(differential_report.disagreements) == 0


def test_zero_soft_disagreements(differential_report) -> None:
    """Validate zero informational violation set discrepancies on invalid cases."""
    if differential_report.soft_disagreements:
        sample_errs = [
            f"Case {d.case_id} ({d.discrepancy_type}): {d.details}"
            for d in differential_report.soft_disagreements[:5]
        ]
        pytest.fail(
            f"Encountered {len(differential_report.soft_disagreements)} soft "
            f"disagreements:\n" + "\n".join(sample_errs)
        )
    assert len(differential_report.soft_disagreements) == 0


def test_cli_subprocess_sample_parity(differential_report) -> None:
    """Validate exit code and first-line parity across 300 subprocess CLI runs."""
    assert differential_report.cli_sample_verified >= 300
    if differential_report.cli_sample_errors:
        pytest.fail(
            f"Encountered {len(differential_report.cli_sample_errors)} CLI errors:\n"
            + "\n".join(differential_report.cli_sample_errors[:5])
        )
    assert len(differential_report.cli_sample_errors) == 0
