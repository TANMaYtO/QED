"""Tests for the circle packing n=26 problem specification and fast evaluator."""

from pathlib import Path
from typing import Any

import numpy as np

from qed.problems.circle_packing_n26.evaluator_fast import (
    evaluate,
    validate_packing,
)
from qed.problems.circle_packing_n26.initial_program import (
    construct_packing,
    run_packing,
)


def test_initial_program_structure_and_bounds() -> None:
    """Verify initial program generates valid arrays within the unit square."""
    centers, radii, sum_radii = run_packing()

    assert isinstance(centers, np.ndarray)
    assert isinstance(radii, np.ndarray)
    assert centers.shape == (26, 2)
    assert radii.shape == (26,)
    assert (radii >= 0.0).all()
    assert sum_radii > 0.0
    assert abs(sum_radii - float(np.sum(radii))) < 1e-9


def test_validate_packing_accepts_valid() -> None:
    """Verify fast evaluator accepts the initial packing configuration."""
    centers, radii, _ = construct_packing()
    assert validate_packing(centers, radii) is True


def test_validate_packing_rejects_boundary_overflow() -> None:
    """Verify fast evaluator rejects circle exceeding square boundary."""
    centers = np.array([[0.05, 0.5]], dtype=float)
    radii = np.array([0.1], dtype=float)  # x - r = -0.05 < 0
    assert validate_packing(centers, radii) is False


def test_validate_packing_rejects_overlap() -> None:
    """Verify fast evaluator rejects overlapping circles."""
    centers = np.array([[0.3, 0.5], [0.4, 0.5]], dtype=float)
    radii = np.array([0.1, 0.1], dtype=float)  # dist=0.1 < r1+r2=0.2
    assert validate_packing(centers, radii) is False


def test_evaluator_fast_end_to_end() -> None:
    """Verify evaluate() runs candidate in subprocess and returns valid score."""
    problem_dir: Path = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "qed"
        / "problems"
        / "circle_packing_n26"
    )
    initial_prog: Path = problem_dir / "initial_program.py"

    metrics: dict[str, Any] = evaluate(str(initial_prog))

    assert metrics["validity"] == 1.0
    assert metrics["sum_radii"] > 0.8
    assert metrics["combined_score"] > 0.0
    assert metrics["eval_time"] >= 0.0
