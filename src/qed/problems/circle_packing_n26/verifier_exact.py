"""Exact rational arithmetic verifier for circle packing (n=26).

Uses fractions.Fraction only. No floating-point operations anywhere in the
checking path. Trust layer guarantee.
"""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

DECIMAL_RE = re.compile(r"^[+-]?(?:\d+\.\d+|\d+\.|\.\d+|\d+)$")
FRACTION_RE = re.compile(r"^[+-]?\d+/[1-9]\d*$")


def parse_exact_fraction(val: Any) -> Fraction:
    """Parse an exact fraction from a 'p/q' or decimal string.

    Rejects floats, scientific notation, NaN, Inf, and strings with trailing junk.
    """
    if not isinstance(val, str):
        raise TypeError(
            f"Expected exact string ('p/q' or decimal), "
            f"got {type(val).__name__}: {val!r}"
        )

    clean: str = val.strip()
    if clean != val or not clean:
        raise ValueError(f"String has invalid whitespace or is empty: {val!r}")

    low: str = val.lower()
    if "e" in low or "nan" in low or "inf" in low:
        raise ValueError(
            "Scientific notation, NaN, and Inf are not allowed in exact "
            f"verification: {val!r}"
        )

    if not (DECIMAL_RE.match(val) or FRACTION_RE.match(val)):
        raise ValueError(f"Invalid exact numeric string: {val!r}")

    try:
        return Fraction(val)
    except Exception as exc:  # pragma: no cover
        raise ValueError(f"Failed to parse exact fraction from {val!r}: {exc}") from exc


def format_fraction_40_decimals(frac: Fraction) -> str:
    """Format Fraction as a decimal string to 40 places using integer division."""
    if frac < 0:
        return f"-{format_fraction_40_decimals(-frac)}"
    p: int = frac.numerator
    q: int = frac.denominator
    integer_part: int = p // q
    remainder: int = p % q
    # Exact 40 decimals computed purely using integer division
    fractional_digits: int = (remainder * (10**40)) // q
    return f"{integer_part}.{fractional_digits:040d}"


def isqrt_lower_bound(ratio: Fraction, precision_scale: int = 10**12) -> Fraction:
    """Compute an exact rational lower bound for sqrt(ratio) using integer square root.

    Given ratio = A/B > 0, we write ratio = (A*B)/B^2.
    Scaling numerator by M^2 gives sqrt(ratio) = sqrt(A*B*M^2) / (B*M).
    Since math.isqrt(K) <= sqrt(K) for all integers K,
    math.isqrt(A*B*M^2) / (B*M) <= sqrt(ratio) is mathematically guaranteed.
    """
    if ratio <= 0:
        return Fraction(0)
    a: int = ratio.numerator
    b: int = ratio.denominator
    m: int = precision_scale
    k: int = math.isqrt(a * b * (m**2))
    bound: Fraction = Fraction(k, b * m)
    # Verification of mathematical guarantee (defensive check)
    if bound * bound > ratio:  # pragma: no cover
        bound = Fraction(k - 1, b * m)
    return bound


@dataclass(frozen=True)
class ConstraintViolation:
    """Describes an exact geometric constraint violation."""

    violation_type: str
    indices: tuple[int, ...]
    slack: Fraction
    details: str


@dataclass(frozen=True)
class VerificationResult:
    """Result of exact rational verification for circle packing."""

    ok: bool
    exact_score: Fraction
    score_decimal: str
    violations: list[ConstraintViolation]


def verify_packing_exact(
    centers: Sequence[Sequence[Any]], radii: Sequence[Any]
) -> VerificationResult:
    """Verify circle packing validity and exact score using exact arithmetic.

    Inputs must be 26 centers (x, y) and 26 radii as exact strings ('p/q' or decimal).
    Returns VerificationResult containing exact score and violations if any.
    """
    violations: list[ConstraintViolation] = []

    # 1. Circle count check
    if len(centers) != 26 or len(radii) != 26:
        violations.append(
            ConstraintViolation(
                violation_type="invalid_circle_count",
                indices=(),
                slack=Fraction(len(centers) - 26),
                details=(
                    f"Expected 26 circles, got {len(centers)} centers "
                    f"and {len(radii)} radii"
                ),
            )
        )
        return VerificationResult(
            ok=False,
            exact_score=Fraction(0),
            score_decimal=format_fraction_40_decimals(Fraction(0)),
            violations=violations,
        )

    # 2. Exact parsing
    exact_centers: list[tuple[Fraction, Fraction]] = []
    exact_radii: list[Fraction] = []

    for i in range(26):
        c = centers[i]
        if len(c) != 2:
            violations.append(
                ConstraintViolation(
                    violation_type="invalid_coordinate_dimension",
                    indices=(i,),
                    slack=Fraction(len(c) - 2),
                    details=f"Circle {i} center has dimension {len(c)}, expected 2",
                )
            )
            return VerificationResult(
                ok=False,
                exact_score=Fraction(0),
                score_decimal=format_fraction_40_decimals(Fraction(0)),
                violations=violations,
            )
        exact_centers.append((parse_exact_fraction(c[0]), parse_exact_fraction(c[1])))
        exact_radii.append(parse_exact_fraction(radii[i]))

    # 3. Radius positivity: r_i > 0
    for i in range(26):
        r: Fraction = exact_radii[i]
        if r <= 0:
            violations.append(
                ConstraintViolation(
                    violation_type="non_positive_radius",
                    indices=(i,),
                    slack=r,
                    details=f"Circle {i} has non-positive radius {r}",
                )
            )

    # 4. Unit square boundary containment: r_i <= x_i <= 1 - r_i, r_i <= y_i <= 1 - r_i
    one = Fraction(1)
    for i in range(26):
        x, y = exact_centers[i]
        r = exact_radii[i]

        left_slack: Fraction = x - r
        if left_slack < 0:
            violations.append(
                ConstraintViolation(
                    violation_type="boundary_left_breach",
                    indices=(i,),
                    slack=left_slack,
                    details=(
                        f"Circle {i} exceeds left boundary: x - r = {left_slack} < 0"
                    ),
                )
            )

        right_slack: Fraction = one - (x + r)
        if right_slack < 0:
            violations.append(
                ConstraintViolation(
                    violation_type="boundary_right_breach",
                    indices=(i,),
                    slack=right_slack,
                    details=(
                        f"Circle {i} exceeds right boundary: "
                        f"1 - (x + r) = {right_slack} < 0"
                    ),
                )
            )

        bottom_slack: Fraction = y - r
        if bottom_slack < 0:
            violations.append(
                ConstraintViolation(
                    violation_type="boundary_bottom_breach",
                    indices=(i,),
                    slack=bottom_slack,
                    details=(
                        f"Circle {i} exceeds bottom boundary: "
                        f"y - r = {bottom_slack} < 0"
                    ),
                )
            )

        top_slack: Fraction = one - (y + r)
        if top_slack < 0:
            violations.append(
                ConstraintViolation(
                    violation_type="boundary_top_breach",
                    indices=(i,),
                    slack=top_slack,
                    details=(
                        f"Circle {i} exceeds top boundary: "
                        f"1 - (y + r) = {top_slack} < 0"
                    ),
                )
            )

    # 5. Non-overlapping pairwise condition:
    # (x_i - x_j)^2 + (y_i - y_j)^2 >= (r_i + r_j)^2
    for i in range(26):
        xi, yi = exact_centers[i]
        ri = exact_radii[i]
        for j in range(i + 1, 26):
            xj, yj = exact_centers[j]
            rj = exact_radii[j]

            dx: Fraction = xi - xj
            dy: Fraction = yi - yj
            dist_sq: Fraction = dx * dx + dy * dy
            radii_sum: Fraction = ri + rj
            radii_sq: Fraction = radii_sum * radii_sum

            overlap_slack: Fraction = dist_sq - radii_sq
            if overlap_slack < 0:
                violations.append(
                    ConstraintViolation(
                        violation_type="circle_overlap",
                        indices=(i, j),
                        slack=overlap_slack,
                        details=(
                            f"Circles {i} and {j} overlap: dist^2 - (ri+rj)^2 = "
                            f"{overlap_slack} < 0"
                        ),
                    )
                )

    exact_score: Fraction = sum(exact_radii, Fraction(0))
    ok: bool = len(violations) == 0

    return VerificationResult(
        ok=ok,
        exact_score=exact_score,
        score_decimal=format_fraction_40_decimals(exact_score),
        violations=violations,
    )


@dataclass(frozen=True)
class ValidConstructionResult:
    """Result of converting a float construction to an exact valid construction."""

    exact_centers: list[tuple[str, str]]
    exact_radii: list[str]
    exact_score: Fraction
    exact_loss: Fraction
    score_decimal: str


def make_valid(
    float_centers: Sequence[Sequence[float]], float_radii: Sequence[float]
) -> ValidConstructionResult:
    """Convert float construction into an exact valid one using integer square roots.

    Methodology:
    1. Losslessly converts float centers and radii into exact rational numbers.
    2. Enforces unit square containment by shrinking radii to min(x, y, 1-x, 1-y).
    3. Resolves pairwise overlaps by computing an exact rational lower bound
       for Euclidean distance between centers using integer square roots:
           d_ij = isqrt(A * B * M^2) / (B * M) <= sqrt(A / B) = dist(C_i, C_j)
       where M = 10^12. If r_i + r_j > d_ij, scales radii down by d_ij / (r_i + r_j).
    4. Enforces a controlled denominator scale Q=10^18 so denominators stay bounded.
    5. Iterates until all pairwise and boundary constraints hold strictly.
    6. Returns exact string representations, exact score, and exact score loss.
    """
    if len(float_centers) != 26 or len(float_radii) != 26:
        raise ValueError(
            f"Expected 26 circles, got {len(float_centers)} centers "
            f"and {len(float_radii)} radii"
        )

    # 1. Lossless conversion from floats
    exact_centers: list[tuple[Fraction, Fraction]] = [
        (Fraction(float(c[0])), Fraction(float(c[1]))) for c in float_centers
    ]
    exact_radii: list[Fraction] = [Fraction(float(r)) for r in float_radii]

    initial_score: Fraction = sum(exact_radii, Fraction(0))
    one = Fraction(1)

    # 2. Boundary containment clamping with precision scale Q=10^18
    q_scale: int = 10**18
    for i in range(26):
        x, y = exact_centers[i]
        boundary_limit: Fraction = min(x, y, one - x, one - y)
        if boundary_limit <= 0:
            exact_radii[i] = Fraction(0)
        else:
            r_clamped: Fraction = min(exact_radii[i], boundary_limit)
            exact_radii[i] = Fraction(math.floor(r_clamped * q_scale), q_scale)

    # 3. Pairwise distance separation with integer square roots
    max_passes: int = 10
    for _ in range(max_passes):
        violation_found: bool = False
        for i in range(26):
            xi, yi = exact_centers[i]
            for j in range(i + 1, 26):
                xj, yj = exact_centers[j]
                dx = xi - xj
                dy = yi - yj
                dist_sq = dx * dx + dy * dy

                d_lower: Fraction = isqrt_lower_bound(dist_sq, precision_scale=10**12)
                sum_r: Fraction = exact_radii[i] + exact_radii[j]
                if sum_r > d_lower:
                    violation_found = True
                    if sum_r > 0:
                        scale: Fraction = d_lower / sum_r
                        exact_radii[i] = Fraction(
                            math.floor(exact_radii[i] * scale * q_scale), q_scale
                        )
                        exact_radii[j] = Fraction(
                            math.floor(exact_radii[j] * scale * q_scale), q_scale
                        )
                    else:  # pragma: no cover
                        exact_radii[i] = Fraction(0)
                        exact_radii[j] = Fraction(0)
        if not violation_found:
            break

    # Ensure non-negative radii (defensive check)
    for i in range(26):
        if exact_radii[i] < 0:  # pragma: no cover
            exact_radii[i] = Fraction(0)

    final_score: Fraction = sum(exact_radii, Fraction(0))
    exact_loss: Fraction = initial_score - final_score

    # Convert to exact strings ('p/q')
    str_centers = [
        (
            f"{c[0].numerator}/{c[0].denominator}",
            f"{c[1].numerator}/{c[1].denominator}",
        )
        for c in exact_centers
    ]
    str_radii = [f"{r.numerator}/{r.denominator}" for r in exact_radii]

    return ValidConstructionResult(
        exact_centers=str_centers,
        exact_radii=str_radii,
        exact_score=final_score,
        exact_loss=exact_loss,
        score_decimal=format_fraction_40_decimals(final_score),
    )
