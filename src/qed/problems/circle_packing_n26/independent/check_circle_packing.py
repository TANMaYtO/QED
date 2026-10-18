"""Circle packing verification script for a unit square with n=26.

This module independently validates circle packing construction files in exact
rational arithmetic without using floating-point arithmetic.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
import sys
from typing import Any

DECIMAL_PATTERN = re.compile(r"^[+-]?(?:[0-9]+\.[0-9]+|[0-9]+\.|\.[0-9]+|[0-9]+)\Z")
FRACTION_PATTERN = re.compile(r"^[+-]?[0-9]+/[1-9][0-9]*\Z")


class FormatError(Exception):
    """Raised when a construction file violates format or grammar rules."""


def check_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Validate that no duplicate keys exist in a JSON object.

    Args:
        pairs: A list of key-value tuples from JSON decoding.

    Returns:
        A dictionary containing the parsed pairs.

    Raises:
        ValueError: If any key appears more than once.
    """
    seen_keys: set[str] = set()
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen_keys:
            raise ValueError(f"duplicate key '{key}'")
        seen_keys.add(key)
        result[key] = value
    return result


def parse_number_string(raw: str) -> tuple[int, int]:
    """Parse a decimal or fraction string into an irreducible rational pair.

    Args:
        raw: The decoded string to parse.

    Returns:
        A tuple (numerator, denominator) with denominator >= 1.

    Raises:
        FormatError: If the string fails any number grammar requirement.
    """
    if len(raw) == 0:
        raise FormatError("empty number string")
    if len(raw) > 100:
        raise FormatError(f"number string exceeds 100 characters: {raw[:20]}...")
    if not raw.isascii():
        raise FormatError(f"number string contains non-ASCII characters: {raw!r}")
    for char in raw:
        code = ord(char)
        if code < 32 or code == 127:
            raise FormatError(
                f"number string contains control character codepoint {code}"
            )

    if DECIMAL_PATTERN.match(raw):
        sign = -1 if raw.startswith("-") else 1
        core = raw[1:] if raw[0] in "+-" else raw
        if "." in core:
            int_part, frac_part = core.split(".")
            k = len(frac_part)
            den = 10**k
            int_val = int(int_part) if int_part else 0
            frac_val = int(frac_part) if frac_part else 0
            num = sign * (int_val * den + frac_val)
        else:
            num = sign * int(core)
            den = 1
    elif FRACTION_PATTERN.match(raw):
        num_str, den_str = raw.split("/")
        sign = -1 if num_str.startswith("-") else 1
        num_core = num_str[1:] if num_str[0] in "+-" else num_str
        num = sign * int(num_core)
        den = int(den_str)
    else:
        raise FormatError(f"invalid number string format: {raw!r}")

    gcd_val = math.gcd(abs(num), den)
    return num // gcd_val, den // gcd_val


def format_rational(num: int, den: int) -> str:
    """Format a rational number as p/q in lowest terms with q >= 1.

    Args:
        num: Rational numerator.
        den: Rational denominator (must be non-zero).

    Returns:
        String formatted as 'p/q'.

    Raises:
        ValueError: If den is 0.
    """
    if den == 0:
        raise ValueError("denominator cannot be zero")
    if den < 0:
        num = -num
        den = -den
    gcd_val = math.gcd(abs(num), den)
    reduced_num = num // gcd_val
    reduced_den = den // gcd_val
    return f"{reduced_num}/{reduced_den}"


def parse_and_validate_json(raw_bytes: bytes) -> dict[str, Any]:
    """Parse raw bytes according to byte-level and JSON schema constraints.

    Args:
        raw_bytes: Binary contents of the construction file.

    Returns:
        Validated top-level dictionary containing 'centers' and 'radii'.

    Raises:
        FormatError: If any byte-level, JSON, or schema check fails.
    """
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        raise FormatError("UTF-8 BOM detected")

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FormatError(f"invalid UTF-8 byte sequence: {exc}") from exc

    allowed_ws = {" ", "\t", "\n", "\r"}
    start_idx = 0
    while start_idx < len(text) and text[start_idx] in allowed_ws:
        start_idx += 1

    if start_idx == len(text):
        raise FormatError("empty or whitespace-only file content")

    decoder = json.JSONDecoder(object_pairs_hook=check_duplicate_keys)
    try:
        obj, end_idx = decoder.raw_decode(text, idx=start_idx)
    except json.JSONDecodeError as exc:
        raise FormatError(f"JSON syntax error: {exc.msg}") from exc
    except ValueError as exc:
        raise FormatError(str(exc)) from exc

    trailing_content = text[end_idx:]
    if any(ch not in allowed_ws for ch in trailing_content):
        raise FormatError("trailing content after top-level JSON value")

    if not isinstance(obj, dict):
        raise FormatError("top-level JSON value must be an object")

    if set(obj.keys()) != {"centers", "radii"}:
        raise FormatError(
            "object must contain exactly two lowercase keys: 'centers' and 'radii'"
        )

    centers_val = obj["centers"]
    radii_val = obj["radii"]

    if not isinstance(centers_val, list):
        raise FormatError("'centers' must be a list")
    if len(centers_val) != 26:
        raise FormatError(
            f"'centers' list must contain exactly 26 items, found {len(centers_val)}"
        )

    if not isinstance(radii_val, list):
        raise FormatError("'radii' must be a list")
    if len(radii_val) != 26:
        raise FormatError(
            f"'radii' list must contain exactly 26 items, found {len(radii_val)}"
        )

    for idx, item in enumerate(centers_val):
        if not isinstance(item, list):
            raise FormatError(f"item at index {idx} in 'centers' must be a list")
        if len(item) != 2:
            raise FormatError(
                f"coordinate pair at index {idx} must have length 2, found {len(item)}"
            )
        x_val, y_val = item
        if type(x_val) is not str or type(y_val) is not str:
            raise FormatError(f"coordinates at index {idx} must be strings")

    for idx, r_val in enumerate(radii_val):
        if type(r_val) is not str:
            raise FormatError(f"radius at index {idx} must be a string")

    return obj


def evaluate_construction(
    data: dict[str, Any],
) -> tuple[bool, str, list[str]]:
    """Evaluate geometric validity of parsed circle packing in exact arithmetic.

    Args:
        data: Validated dictionary containing string centers and radii.

    Returns:
        A tuple of (is_valid, score_str, violation_lines).
    """
    centers_raw: list[list[str]] = data["centers"]
    radii_raw: list[str] = data["radii"]

    parsed_x: list[tuple[int, int]] = []
    parsed_y: list[tuple[int, int]] = []
    parsed_r: list[tuple[int, int]] = []

    for x_str, y_str in centers_raw:
        parsed_x.append(parse_number_string(x_str))
        parsed_y.append(parse_number_string(y_str))

    for r_str in radii_raw:
        parsed_r.append(parse_number_string(r_str))

    denominators: list[int] = []
    for num_x, den_x in parsed_x:
        denominators.append(den_x)
    for num_y, den_y in parsed_y:
        denominators.append(den_y)
    for num_r, den_r in parsed_r:
        denominators.append(den_r)

    common_den = math.lcm(*denominators)

    scaled_x: list[int] = [nx * (common_den // dx) for nx, dx in parsed_x]
    scaled_y: list[int] = [ny * (common_den // dy) for ny, dy in parsed_y]
    scaled_r: list[int] = [nr * (common_den // dr) for nr, dr in parsed_r]

    violations: list[str] = []

    for i in range(26):
        xi = scaled_x[i]
        yi = scaled_y[i]
        ri = scaled_r[i]

        if ri <= 0:
            slack_str = format_rational(ri, common_den)
            violations.append(f"non_positive_radius: indices={(i,)}, slack={slack_str}")

        left_slack = xi - ri
        if left_slack < 0:
            slack_str = format_rational(left_slack, common_den)
            violations.append(
                f"boundary_left_breach: indices={(i,)}, slack={slack_str}"
            )

        right_slack = common_den - (xi + ri)
        if right_slack < 0:
            slack_str = format_rational(right_slack, common_den)
            violations.append(
                f"boundary_right_breach: indices={(i,)}, slack={slack_str}"
            )

        bottom_slack = yi - ri
        if bottom_slack < 0:
            slack_str = format_rational(bottom_slack, common_den)
            violations.append(
                f"boundary_bottom_breach: indices={(i,)}, slack={slack_str}"
            )

        top_slack = common_den - (yi + ri)
        if top_slack < 0:
            slack_str = format_rational(top_slack, common_den)
            violations.append(f"boundary_top_breach: indices={(i,)}, slack={slack_str}")

    common_den_sq = common_den * common_den
    for i in range(26):
        xi = scaled_x[i]
        yi = scaled_y[i]
        ri = scaled_r[i]
        for j in range(i + 1, 26):
            xj = scaled_x[j]
            yj = scaled_y[j]
            rj = scaled_r[j]

            dx = xi - xj
            dy = yi - yj
            r_sum = ri + rj
            overlap_slack_num = (dx * dx + dy * dy) - (r_sum * r_sum)
            if overlap_slack_num < 0:
                slack_str = format_rational(overlap_slack_num, common_den_sq)
                violations.append(
                    f"circle_overlap: indices={(i, j)}, slack={slack_str}"
                )

    total_radius_num = sum(scaled_r)
    score_str = format_rational(total_radius_num, common_den)

    is_valid = len(violations) == 0
    return is_valid, score_str, violations


def _read_bytes_sync(filepath: str) -> bytes:
    """Read file content synchronously as bytes.

    Args:
        filepath: Path to the target file.

    Returns:
        Raw bytes read from the file.
    """
    with open(filepath, "rb") as file_handle:
        return file_handle.read()


async def read_file_bytes(filepath: str) -> bytes:
    """Read file content asynchronously as bytes.

    Args:
        filepath: Path to the target file.

    Returns:
        Raw bytes read from the file.
    """
    return await asyncio.to_thread(_read_bytes_sync, filepath)


async def check_construction_file(filepath: str) -> tuple[int, list[str]]:
    """Verify a construction file from path and return exit code and output.

    Args:
        filepath: Path to the JSON construction file.

    Returns:
        A tuple of (exit_code, output_lines).
    """
    try:
        raw_bytes = await read_file_bytes(filepath)
    except OSError:
        return 1, ["INVALID format_error: cannot read file"]

    try:
        data = parse_and_validate_json(raw_bytes)
        is_valid, score_str, violations = evaluate_construction(data)
    except FormatError as exc:
        return 1, [f"INVALID format_error: {exc}"]

    if is_valid:
        return 0, [f"VALID {score_str}"]

    output_lines = ["INVALID"]
    output_lines.extend(violations)
    return 1, output_lines


async def async_main(argv: list[str]) -> int:
    """Run verification asynchronously from command-line arguments.

    Args:
        argv: Command-line arguments including script name.

    Returns:
        Process exit code (0 for valid, 1 for invalid or error).
    """
    if len(argv) != 2:
        print("INVALID format_error: usage: python check_circle_packing.py <file>")
        return 1

    filepath = argv[1]
    exit_code, lines = await check_construction_file(filepath)
    for line in lines:
        print(line)
    return exit_code


def main() -> None:
    """Synchronous entry point that invokes the async runner."""
    exit_code = asyncio.run(async_main(sys.argv))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
