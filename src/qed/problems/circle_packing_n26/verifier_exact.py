"""Exact rational arithmetic verifier for circle packing (n=26).

Uses fractions.Fraction only. No floating-point operations anywhere in the
checking path. Trust layer guarantee.
"""

import asyncio
import json
import math
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

DECIMAL_RE = re.compile(r"^[+-]?(?:[0-9]+\.[0-9]+|[0-9]+\.|\.[0-9]+|[0-9]+)\Z")
FRACTION_RE = re.compile(r"^[+-]?[0-9]+/[1-9][0-9]*\Z")


def parse_exact_fraction(val: Any) -> Fraction:
    """Parse an exact fraction from a 'p/q' or decimal string.

    Rejects floats, scientific notation, NaN, Inf, non-ASCII, control characters,
    strings exceeding 100 characters, and strings with trailing junk.
    """
    if not isinstance(val, str):
        raise TypeError(
            f"Expected exact string ('p/q' or decimal), "
            f"got {type(val).__name__}: {val!r}"
        )

    if len(val) > 100:
        raise ValueError(
            "Number string exceeds maximum allowed length of 100 characters: "
            f"{len(val)}"
        )

    if not val.isascii():
        raise ValueError(
            f"Non-ASCII characters are not allowed in exact numeric strings: {val!r}"
        )

    if any(ord(c) < 32 or ord(c) == 127 for c in val):
        raise ValueError(
            f"Control characters are not allowed in exact numeric strings: {val!r}"
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
                violation_type="format_error",
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
                    violation_type="format_error",
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


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Construct a dictionary from key-value pairs while rejecting duplicate keys."""
    res: dict[str, Any] = {}
    for key, val in pairs:
        if key in res:
            raise ValueError(f"Duplicate key in JSON construction object: {key!r}")
        res[key] = val
    return res


def parse_construction_json(
    json_str: str,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Parse and strictly validate a construction JSON string.

    Enforces the specification grammar:
    - Top-level object with exactly two keys: 'centers' and 'radii'.
    - No duplicate or extra keys.
    - 'centers' must be a list of 26 two-element string lists.
    - 'radii' must be a list of 26 strings.
    - Every string must satisfy parse_exact_fraction grammar.
    """
    if json_str.startswith("\ufeff"):
        raise ValueError("UTF-8 byte-order mark (BOM) is not allowed")

    try:
        data = json.loads(json_str, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON content: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"Top-level JSON value must be an object, got {type(data).__name__}"
        )

    expected_keys = {"centers", "radii"}
    actual_keys = set(data.keys())

    missing = expected_keys - actual_keys
    if missing:
        raise ValueError(f"Missing required key(s) in construction: {sorted(missing)}")

    extra = actual_keys - expected_keys
    if extra:
        raise ValueError(f"Unexpected extra key(s) in construction: {sorted(extra)}")

    raw_centers = data["centers"]
    if not isinstance(raw_centers, list) or len(raw_centers) != 26:
        actual_centers_len = (
            str(len(raw_centers))
            if isinstance(raw_centers, list)
            else type(raw_centers).__name__
        )
        raise ValueError(
            "Key 'centers' must be a list of exactly 26 coordinate pairs, "
            f"got {actual_centers_len}"
        )

    raw_radii = data["radii"]
    if not isinstance(raw_radii, list) or len(raw_radii) != 26:
        actual_radii_len = (
            str(len(raw_radii))
            if isinstance(raw_radii, list)
            else type(raw_radii).__name__
        )
        raise ValueError(
            f"Key 'radii' must be a list of exactly 26 strings, got {actual_radii_len}"
        )

    validated_centers: list[tuple[str, str]] = []
    for i, pair in enumerate(raw_centers):
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError(
                f"Circle {i} center must be a 2-element list [x, y], got {pair!r}"
            )
        x_str, y_str = pair[0], pair[1]
        if not isinstance(x_str, str) or not isinstance(y_str, str):
            raise TypeError(
                f"Circle {i} center coordinates must be strings, "
                f"got ({type(x_str).__name__}, {type(y_str).__name__})"
            )
        # Validate exact rational grammar
        parse_exact_fraction(x_str)
        parse_exact_fraction(y_str)
        validated_centers.append((x_str, y_str))

    validated_radii: list[str] = []
    for i, r_val in enumerate(raw_radii):
        if not isinstance(r_val, str):
            raise TypeError(
                f"Circle {i} radius must be a string, got {type(r_val).__name__}"
            )
        # Validate exact rational grammar
        parse_exact_fraction(r_val)
        validated_radii.append(r_val)

    return validated_centers, validated_radii


def load_construction(
    path: str | Path,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Read and validate a 26-circle construction JSON file from disk."""
    file_path: Path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Construction file not found: {file_path}")
    raw_bytes: bytes = file_path.read_bytes()
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF-8 byte-order mark (BOM) is not allowed")
    try:
        content: str = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Invalid UTF-8 encoding in construction file: {exc}") from exc
    return parse_construction_json(content)


async def load_construction_async(
    path: str | Path,
) -> tuple[list[tuple[str, str]], list[str]]:
    """Asynchronously read and validate a 26-circle construction JSON file."""
    file_path: Path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Construction file not found: {file_path}")
    raw_bytes: bytes = await asyncio.to_thread(file_path.read_bytes)
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        raise ValueError("UTF-8 byte-order mark (BOM) is not allowed")
    try:
        content: str = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Invalid UTF-8 encoding in construction file: {exc}") from exc
    return parse_construction_json(content)


def verify_construction_file(path: str | Path) -> VerificationResult:
    """Load a construction JSON file and verify its exact geometric validity."""
    centers, radii = load_construction(path)
    return verify_packing_exact(centers, radii)


async def verify_construction_file_async(
    path: str | Path,
) -> VerificationResult:
    """Asynchronously load a construction JSON file and verify its exact validity."""
    centers, radii = await load_construction_async(path)
    return verify_packing_exact(centers, radii)


def format_verification_output(result: VerificationResult) -> str:
    """Format VerificationResult according to the specification output convention."""
    if result.ok:
        score_str: str = (
            f"{result.exact_score.numerator}/{result.exact_score.denominator}"
        )
        return f"VALID {score_str}"

    format_errors = [v for v in result.violations if v.violation_type == "format_error"]
    if format_errors:
        return f"INVALID format_error: {format_errors[0].details}"

    count: int = len(result.violations)
    noun: str = "violation" if count == 1 else "violations"
    lines: list[str] = [f"INVALID {count} {noun}"]
    for v in result.violations:
        lines.append(f"{v.violation_type}: indices={v.indices}, slack={v.slack}")
    return "\n".join(lines)


def verify_file_cli(path: str | Path) -> int:
    """Verify construction file from CLI, print result and return code."""
    try:
        result: VerificationResult = verify_construction_file(path)
        print(format_verification_output(result))
        return 0 if result.ok else 1
    except (ValueError, TypeError, FileNotFoundError) as exc:
        print(f"INVALID format_error: {exc}")
        return 1


def main() -> None:
    """CLI entry point for exact verifier."""
    if len(sys.argv) < 2:
        print("INVALID format_error: No input file specified")
        sys.exit(1)
    code: int = verify_file_cli(sys.argv[1])
    sys.exit(code)


if __name__ == "__main__":  # pragma: no cover
    main()
