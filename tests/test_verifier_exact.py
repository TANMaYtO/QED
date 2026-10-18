"""Tests for exact rational arithmetic verifier (circle_packing_n26).

Covers exact verification, precision checks, violation detection,
infinitesimal nudges (10^-18), property-based testing with Hypothesis,
and make_valid shrinker.
"""

from fractions import Fraction

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from qed.problems.circle_packing_n26.verifier_exact import (
    format_fraction_40_decimals,
    isqrt_lower_bound,
    make_valid,
    parse_exact_fraction,
    verify_packing_exact,
)


def make_valid_26_packing() -> tuple[list[tuple[str, str]], list[str]]:
    """Build a known valid 26-circle packing on a 5x5 grid plus one circle."""
    centers: list[tuple[str, str]] = []
    radii: list[str] = []
    # 5x5 grid of 25 circles of radius 1/10
    for i in range(5):
        for j in range(5):
            centers.append((f"{2 * i + 1}/10", f"{2 * j + 1}/10"))
            radii.append("1/10")
    # 26th circle placed in the interstitial space at (1/5, 1/5) with radius 1/30
    centers.append(("1/5", "1/5"))
    radii.append("1/30")
    return centers, radii


def test_parse_exact_fraction_valid() -> None:
    """Test valid fraction and decimal strings parse cleanly."""
    assert parse_exact_fraction("0") == Fraction(0)
    assert parse_exact_fraction("1") == Fraction(1)
    assert parse_exact_fraction("-5") == Fraction(-5)
    assert parse_exact_fraction("1/2") == Fraction(1, 2)
    assert parse_exact_fraction("-3/4") == Fraction(-3, 4)
    assert parse_exact_fraction("0.5") == Fraction(1, 2)
    assert parse_exact_fraction(".5") == Fraction(1, 2)
    assert parse_exact_fraction("5.") == Fraction(5)
    assert parse_exact_fraction("-0.125") == Fraction(-1, 8)
    assert parse_exact_fraction("12345/67890") == Fraction(12345, 67890)


def test_parse_exact_fraction_reject_types() -> None:
    """Test parse_exact_fraction rejects non-string types."""
    for invalid in [123, 0.5, Fraction(1, 2), None, [], {}]:
        with pytest.raises(TypeError, match="Expected exact string"):
            parse_exact_fraction(invalid)


def test_parse_exact_fraction_reject_strings() -> None:
    """Test parse_exact_fraction rejects scientific notation, NaN, Inf, and junk."""
    invalid_strings = [
        "",
        "   ",
        " 1/2",
        "1/2 ",
        "1e-5",
        "2.5E+3",
        "-1e0",
        "nan",
        "NaN",
        "inf",
        "-Inf",
        "infinity",
        "1/0",
        "1/-2",
        "1/2/3",
        "1.2.3",
        "abc",
        "1/2abc",
        "++1",
        "--1",
    ]
    for s in invalid_strings:
        with pytest.raises(ValueError):
            parse_exact_fraction(s)


def test_format_fraction_40_decimals() -> None:
    """Test exact formatting of fractions to 40 decimal places."""
    assert format_fraction_40_decimals(Fraction(0)) == "0." + "0" * 40
    assert format_fraction_40_decimals(Fraction(1, 2)) == "0.5" + "0" * 39
    assert format_fraction_40_decimals(Fraction(1, 3)) == "0." + "3" * 40
    assert format_fraction_40_decimals(Fraction(-5, 4)) == "-1.25" + "0" * 38
    assert format_fraction_40_decimals(Fraction(10, 1)) == "10." + "0" * 40

    # Seventh test
    seventh_40 = "0." + ("142857" * 7)[:40]
    assert format_fraction_40_decimals(Fraction(1, 7)) == seventh_40

    # Ensure format always has 40 digits after the decimal point
    formatted = format_fraction_40_decimals(Fraction(355, 113))
    parts = formatted.split(".")
    assert len(parts) == 2
    assert len(parts[1]) == 40


def test_isqrt_lower_bound() -> None:
    """Test mathematical guarantees of the integer square root lower bound."""
    assert isqrt_lower_bound(Fraction(0)) == Fraction(0)
    assert isqrt_lower_bound(Fraction(-1)) == Fraction(0)
    assert isqrt_lower_bound(Fraction(1, 4)) == Fraction(1, 2)
    assert isqrt_lower_bound(Fraction(4, 9)) == Fraction(2, 3)
    assert isqrt_lower_bound(Fraction(9, 16)) == Fraction(3, 4)

    # Inexact square root
    bound_2 = isqrt_lower_bound(Fraction(2))
    assert bound_2 * bound_2 <= Fraction(2)
    diff = Fraction(2) - bound_2 * bound_2
    assert diff < Fraction(1, 10**11)


def test_valid_packing_passes() -> None:
    """Test that a hand-constructed valid packing passes exact verification."""
    centers, radii = make_valid_26_packing()
    res = verify_packing_exact(centers, radii)

    assert res.ok is True
    assert len(res.violations) == 0
    # Expected score: 25 * (1/10) + 1/30 = 5/2 + 1/30 = 76/30 = 38/15
    assert res.exact_score == Fraction(38, 15)
    assert res.score_decimal == "2.5333333333333333333333333333333333333333"


def test_circle_count_violation() -> None:
    """Test violation when circle count is not 26."""
    centers, radii = make_valid_26_packing()
    # 25 circles
    res_25 = verify_packing_exact(centers[:25], radii[:25])
    assert res_25.ok is False
    assert len(res_25.violations) == 1
    assert res_25.violations[0].violation_type == "invalid_circle_count"

    # 27 circles
    res_27 = verify_packing_exact(centers + [("1/2", "1/2")], radii + ["1/10"])
    assert res_27.ok is False
    assert res_27.violations[0].violation_type == "invalid_circle_count"


def test_invalid_coordinate_dimension() -> None:
    """Test violation when a center does not have 2 coordinates."""
    centers, radii = make_valid_26_packing()
    centers[0] = ("1/2",)  # type: ignore[assignment]
    res = verify_packing_exact(centers, radii)
    assert res.ok is False
    assert len(res.violations) == 1
    assert res.violations[0].violation_type == "invalid_coordinate_dimension"


def test_non_positive_radius_violation() -> None:
    """Test violation when radius is zero or negative."""
    centers, radii = make_valid_26_packing()
    radii[0] = "0"
    res_zero = verify_packing_exact(centers, radii)
    assert res_zero.ok is False
    assert any(v.violation_type == "non_positive_radius" for v in res_zero.violations)

    radii[0] = "-1/10"
    res_neg = verify_packing_exact(centers, radii)
    assert res_neg.ok is False
    assert any(
        v.violation_type == "non_positive_radius" and v.slack == Fraction(-1, 10)
        for v in res_neg.violations
    )


def test_boundary_breaches() -> None:
    """Test left, right, bottom, and top boundary breach detections."""
    # Left breach
    centers, radii = make_valid_26_packing()
    centers[0] = ("0.05", "0.5")
    radii[0] = "0.1"
    res_left = verify_packing_exact(centers, radii)
    assert any(
        v.violation_type == "boundary_left_breach" and v.slack == Fraction(-5, 100)
        for v in res_left.violations
    )

    # Right breach
    centers, radii = make_valid_26_packing()
    centers[0] = ("0.95", "0.5")
    radii[0] = "0.1"
    res_right = verify_packing_exact(centers, radii)
    assert any(
        v.violation_type == "boundary_right_breach" and v.slack == Fraction(-5, 100)
        for v in res_right.violations
    )

    # Bottom breach
    centers, radii = make_valid_26_packing()
    centers[0] = ("0.5", "0.05")
    radii[0] = "0.1"
    res_bottom = verify_packing_exact(centers, radii)
    assert any(
        v.violation_type == "boundary_bottom_breach" and v.slack == Fraction(-5, 100)
        for v in res_bottom.violations
    )

    # Top breach
    centers, radii = make_valid_26_packing()
    centers[0] = ("0.5", "0.95")
    radii[0] = "0.1"
    res_top = verify_packing_exact(centers, radii)
    assert any(
        v.violation_type == "boundary_top_breach" and v.slack == Fraction(-5, 100)
        for v in res_top.violations
    )


def test_circle_overlap_violation() -> None:
    """Test pairwise circle overlap detection with exact rational slack."""
    centers, radii = make_valid_26_packing()
    # Move circle 1 closer to circle 0 so they overlap
    centers[1] = ("2/10", "1/10")  # dist is 1/10, but sum of radii is 2/10
    res = verify_packing_exact(centers, radii)
    assert res.ok is False
    overlap_violations = [
        v for v in res.violations if v.violation_type == "circle_overlap"
    ]
    assert len(overlap_violations) >= 1
    # Check slack: dist^2 - (r0+r1)^2 = (1/10)^2 - (2/10)^2 = 1/100 - 4/100 = -3/100
    v01 = [v for v in overlap_violations if v.indices == (0, 1)][0]
    assert v01.slack == Fraction(-3, 100)


def test_high_precision_slack_1e15() -> None:
    """Test exact detection of micro-overlaps down to 10^-15."""
    centers, radii = make_valid_26_packing()
    # In the valid 5x5 grid:
    # Circle 6 is at (3/10, 3/10) with r=1/10
    # Circle 7 is at (3/10, 5/10) with r=1/10
    # Centers distance is 2/10, radii sum is 2/10. Exactly tangent.
    # Nudge r6 by 1/10^15
    delta = Fraction(1, 10**15)
    r6_nudged = Fraction(1, 10) + delta
    radii[6] = f"{r6_nudged.numerator}/{r6_nudged.denominator}"

    res = verify_packing_exact(centers, radii)
    assert res.ok is False
    overlap_v = [v for v in res.violations if v.indices == (6, 7)]
    assert len(overlap_v) == 1
    # Exact slack: (2/10)^2 - (2/10 + delta)^2 = - (4/10 * delta + delta^2)
    expected_slack = -(Fraction(4, 10) * delta + delta * delta)
    assert overlap_v[0].slack == expected_slack


def test_infinitesimal_nudge_1e18() -> None:
    """Test that nudging an exact tangent outward by 10^-18 triggers an overlap."""
    centers, radii = make_valid_26_packing()
    # In the valid 5x5 grid:
    # Circle 12 is at (5/10, 5/10) with r=1/10
    # Circle 13 is at (5/10, 7/10) with r=1/10
    # Centers are strictly interior: (5/10, 5/10) has distance 5/10 to boundary.
    # Radii sum is 2/10, distance is 2/10. Exact tangency.
    # Nudge r12 by 1/10^18:
    delta = Fraction(1, 10**18)
    r12_nudged = Fraction(1, 10) + delta
    radii[12] = f"{r12_nudged.numerator}/{r12_nudged.denominator}"

    res = verify_packing_exact(centers, radii)
    assert res.ok is False

    # Check that overlap with circle 13 was detected
    overlap_12_13 = [v for v in res.violations if v.indices == (12, 13)]
    assert len(overlap_12_13) == 1
    expected_slack = -(Fraction(4, 10) * delta + delta * delta)
    assert overlap_12_13[0].slack == expected_slack
    # Boundary constraints still hold for Circle 12:
    # 5/10 - 1/10 - 10^-18 = 4/10 - 10^-18 > 0
    assert not any(v.violation_type.startswith("boundary") for v in res.violations)


def test_make_valid_invalid_inputs() -> None:
    """Test make_valid raises ValueError on invalid inputs."""
    with pytest.raises(ValueError, match="Expected 26 circles"):
        make_valid([[0.5, 0.5]] * 25, [0.1] * 25)

    with pytest.raises(ValueError, match="Expected 26 circles"):
        make_valid([[0.5, 0.5]] * 27, [0.1] * 27)


def test_make_valid_resolves_overlaps() -> None:
    """Test make_valid shrinks overlapping float circles to strictly valid packing."""
    # 26 circles all overlapping with radius 0.2
    centers = [[0.1 + (i % 5) * 0.18, 0.1 + (i // 5) * 0.15] for i in range(26)]
    radii = [0.2 for _ in range(26)]

    res = make_valid(centers, radii)
    assert res.exact_loss > 0
    assert res.exact_score > 0

    # Verification must pass with 0 violations
    v = verify_packing_exact(res.exact_centers, res.exact_radii)
    assert v.ok is True
    assert len(v.violations) == 0


def test_make_valid_boundary_and_edge_cases() -> None:
    """Test make_valid with centers on/outside boundary and negative radii."""
    # Centers where some are on or outside boundary
    centers = [[0.0, 0.5]] + [[0.5, 0.5] for _ in range(25)]
    radii = [-0.1] + [0.0 for _ in range(25)]
    res = make_valid(centers, radii)
    assert res.exact_score == Fraction(0)
    assert res.exact_centers[0] == ("0/1", "1/2")


@settings(max_examples=25)
@given(
    st.lists(
        st.tuples(
            st.integers(min_value=1, max_value=8),
            st.integers(min_value=1, max_value=8),
        ),
        min_size=26,
        max_size=26,
        unique=True,
    ),
    st.lists(
        st.floats(min_value=0.01, max_value=0.1),
        min_size=26,
        max_size=26,
    ),
)
def test_hypothesis_make_valid_always_exact_valid(
    grid_coords: list[tuple[int, int]], radii: list[float]
) -> None:
    """Hypothesis test: make_valid with distinct centers is ALWAYS verified as valid."""
    centers = [(x / 10.0, y / 10.0) for x, y in grid_coords]
    res = make_valid(centers, radii)
    v = verify_packing_exact(res.exact_centers, res.exact_radii)
    assert v.ok is True
    assert len(v.violations) == 0


@settings(max_examples=50)
@given(
    st.integers(min_value=1, max_value=10000), st.integers(min_value=1, max_value=10000)
)
def test_hypothesis_isqrt_guarantee(p: int, q: int) -> None:
    """Hypothesis test: isqrt_lower_bound squared is always <= ratio."""
    ratio = Fraction(p, q)
    bound = isqrt_lower_bound(ratio)
    assert bound * bound <= ratio
