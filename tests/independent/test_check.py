"""Test suite for circle packing verification script (check_circle_packing.py).

Covers valid constructions, geometric violations, tangencies, format errors,
and all spec table grammar test cases.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from qed.problems.circle_packing_n26.independent import check_circle_packing


def run_async(coro: Any) -> Any:
    """Run an asynchronous coroutine synchronously for pytest execution.

    Args:
        coro: Coroutine to execute.

    Returns:
        The result returned by the coroutine.
    """
    return asyncio.run(coro)


def _write_bytes_sync(target_path: Path, data: bytes) -> None:
    """Synchronously write raw bytes to target path.

    Args:
        target_path: Destination file path.
        data: Raw byte content to write.
    """
    target_path.write_bytes(data)


async def async_write_file(target_path: Path, data: bytes) -> None:
    """Asynchronously write raw bytes to target path.

    Args:
        target_path: Destination file path.
        data: Raw byte content to write.
    """
    await asyncio.to_thread(_write_bytes_sync, target_path, data)


def make_valid_grid_construction() -> dict[str, Any]:
    """Build a valid 26-circle configuration on a 6x6 grid with radius 1/12.

    Returns:
        A dictionary containing 'centers' and 'radii'.
    """
    centers: list[list[str]] = []
    radii: list[str] = []
    count = 0
    for u in range(6):
        for v in range(6):
            if count < 26:
                x_val = f"{2 * u + 1}/12"
                y_val = f"{2 * v + 1}/12"
                centers.append([x_val, y_val])
                radii.append("1/12")
                count += 1
    return {"centers": centers, "radii": radii}


def test_valid_grid_packing(tmp_path: Path) -> None:
    """Test a valid 26-circle packing on a 6x6 grid with score 13/6."""

    async def run() -> None:
        data = make_valid_grid_construction()
        json_path = tmp_path / "valid_grid.json"
        raw_bytes = json.dumps(data).encode("utf-8")
        await async_write_file(json_path, raw_bytes)

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 0
        assert lines == ["VALID 13/6"]

    run_async(run())


def test_valid_varying_radii(tmp_path: Path) -> None:
    """Test a valid packing with one larger circle and 25 tiny circles."""

    async def run() -> None:
        data = make_valid_grid_construction()
        # Circle 0 at center (1/2, 1/2) with radius 1/4
        data["centers"][0] = ["1/2", "1/2"]
        data["radii"][0] = "1/4"
        # Circles 1..25 far away with small radius 1/100
        for i in range(1, 26):
            # Place in safe corner near (1/10, 1/10) to (1/10, 1/5)
            data["centers"][i] = [f"{(i * 3)}/100", "1/10"]
            data["radii"][i] = "1/100"

        json_path = tmp_path / "valid_varying.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 0
        # Score = 1/4 + 25 * 1/100 = 1/4 + 1/4 = 1/2
        assert lines == ["VALID 1/2"]

    run_async(run())


def test_exact_pythagorean_tangency(tmp_path: Path) -> None:
    """Test exact circle-circle tangency using 3-4-5 right triangle and bounds."""

    async def run() -> None:
        data = make_valid_grid_construction()
        # Circle 0: tangent to left and bottom boundary
        # x0 = 1/10, y0 = 1/10, r0 = 1/10 -> x0 - r0 = 0, y0 - r0 = 0
        data["centers"][0] = ["1/10", "1/10"]
        data["radii"][0] = "1/10"
        # Circle 1: dx = 3/20, dy = 4/20, dist = 5/20 = 1/4
        # r0 = 2/20 = 1/10, r1 = 3/20, r0 + r1 = 5/20. Exact tangency!
        # x1 = 1/10 + 3/20 = 5/20 = 1/4, y1 = 1/10 + 4/20 = 6/20 = 3/10
        data["centers"][1] = ["1/4", "3/10"]
        data["radii"][1] = "3/20"
        # Circle 2: tangent to right and top boundary: x = 9/10, y = 9/10, r = 1/10
        data["centers"][2] = ["9/10", "9/10"]
        data["radii"][2] = "1/10"
        # Remaining circles 3..25 far away in [0.7, 0.85] range
        for i in range(3, 26):
            data["centers"][i] = ["7/10", f"{i}/40"]
            data["radii"][i] = "1/100"

        json_path = tmp_path / "pythagorean_tangency.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 0
        assert lines[0].startswith("VALID ")

    run_async(run())


def test_violation_non_positive_radius(tmp_path: Path) -> None:
    """Test geometric violation: non_positive_radius."""

    async def run() -> None:
        data = make_valid_grid_construction()
        data["radii"][5] = "0"

        json_path = tmp_path / "zero_radius.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0] == "INVALID"
        assert any(
            "non_positive_radius: indices=(5,), slack=0/1" in line for line in lines[1:]
        )

    run_async(run())


def test_violation_negative_radius(tmp_path: Path) -> None:
    """Test geometric violation: strictly negative radius."""

    async def run() -> None:
        data = make_valid_grid_construction()
        data["radii"][2] = "-1/12"

        json_path = tmp_path / "neg_radius.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0] == "INVALID"
        assert any(
            "non_positive_radius: indices=(2,), slack=-1/12" in line
            for line in lines[1:]
        )

    run_async(run())


def test_violation_boundary_left_breach(tmp_path: Path) -> None:
    """Test geometric violation: boundary_left_breach."""

    async def run() -> None:
        data = make_valid_grid_construction()
        # xi = 1/20, ri = 1/10 -> xi - ri = -1/20 < 0
        data["centers"][0] = ["1/20", "1/2"]
        data["radii"][0] = "1/10"

        json_path = tmp_path / "left_breach.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0] == "INVALID"
        assert any(
            "boundary_left_breach: indices=(0,), slack=-1/20" in line
            for line in lines[1:]
        )

    run_async(run())


def test_violation_boundary_right_breach(tmp_path: Path) -> None:
    """Test geometric violation: boundary_right_breach."""

    async def run() -> None:
        data = make_valid_grid_construction()
        # xi = 9/10, ri = 2/10 -> 1 - (xi + ri) = -1/10 < 0
        data["centers"][0] = ["9/10", "1/2"]
        data["radii"][0] = "2/10"

        json_path = tmp_path / "right_breach.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0] == "INVALID"
        assert any(
            "boundary_right_breach: indices=(0,), slack=-1/10" in line
            for line in lines[1:]
        )

    run_async(run())


def test_violation_boundary_bottom_breach(tmp_path: Path) -> None:
    """Test geometric violation: boundary_bottom_breach."""

    async def run() -> None:
        data = make_valid_grid_construction()
        # yi = 1/20, ri = 1/10 -> yi - ri = -1/20 < 0
        data["centers"][3] = ["1/2", "1/20"]
        data["radii"][3] = "1/10"

        json_path = tmp_path / "bottom_breach.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0] == "INVALID"
        assert any(
            "boundary_bottom_breach: indices=(3,), slack=-1/20" in line
            for line in lines[1:]
        )

    run_async(run())


def test_violation_boundary_top_breach(tmp_path: Path) -> None:
    """Test geometric violation: boundary_top_breach."""

    async def run() -> None:
        data = make_valid_grid_construction()
        # yi = 9/10, ri = 2/10 -> 1 - (yi + ri) = -1/10 < 0
        data["centers"][4] = ["1/2", "9/10"]
        data["radii"][4] = "2/10"

        json_path = tmp_path / "top_breach.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0] == "INVALID"
        assert any(
            "boundary_top_breach: indices=(4,), slack=-1/10" in line
            for line in lines[1:]
        )

    run_async(run())


def test_violation_circle_overlap(tmp_path: Path) -> None:
    """Test geometric violation: circle_overlap."""

    async def run() -> None:
        data = make_valid_grid_construction()
        # Place circle 0 and circle 1 at same center (1/2, 1/2), radius 1/10
        # dist^2 = 0, (r0 + r1)^2 = (2/10)^2 = 1/25. slack = -1/25
        data["centers"][0] = ["1/2", "1/2"]
        data["radii"][0] = "1/10"
        data["centers"][1] = ["1/2", "1/2"]
        data["radii"][1] = "1/10"

        json_path = tmp_path / "overlap.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0] == "INVALID"
        assert any(
            "circle_overlap: indices=(0, 1), slack=-1/25" in line for line in lines[1:]
        )

    run_async(run())


def test_huge_denominators_near_cap(tmp_path: Path) -> None:
    """Test valid construction with numbers near the 100-character cap."""

    async def run() -> None:
        data = make_valid_grid_construction()
        # Length 100 fraction: '1/' followed by 98 digits
        huge_den = "9" * 98
        huge_frac = f"1/{huge_den}"
        assert len(huge_frac) == 100

        data["radii"][0] = huge_frac
        data["centers"][0] = ["1/2", "1/2"]

        json_path = tmp_path / "huge_den.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 0
        assert lines[0].startswith("VALID ")

    run_async(run())


def test_huge_decimal_near_cap(tmp_path: Path) -> None:
    """Test valid construction with a 100-character decimal string."""

    async def run() -> None:
        data = make_valid_grid_construction()
        # Length 100 decimal: '0.' + 98 digits
        huge_dec = "0." + ("1" * 98)
        assert len(huge_dec) == 100

        data["centers"][0] = [huge_dec, "1/2"]
        data["radii"][0] = "1/100"
        for i in range(1, 26):
            data["centers"][i] = [f"{(i * 3)}/100", "1/10"]
            data["radii"][i] = "1/100"

        json_path = tmp_path / "huge_dec.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 0
        assert lines[0].startswith("VALID ")

    run_async(run())


@pytest.mark.parametrize(
    "raw_str, expected",
    [
        ("0", (0, 1)),
        ("1", (1, 1)),
        ("-5", (-5, 1)),
        ("+7", (7, 1)),
        ("0.5", (1, 2)),
        (".5", (1, 2)),
        ("5.", (5, 1)),
        ("-0.125", (-1, 8)),
        ("+007.25", (29, 4)),
        ("1/2", (1, 2)),
        ("-3/4", (-3, 4)),
        ("+26/1", (26, 1)),
        ("12345/67890", (823, 4526)),
        ("0/1", (0, 1)),
    ],
)
def test_spec_accepted_number_strings(raw_str: str, expected: tuple[int, int]) -> None:
    """Test all accepted number strings from spec section 5.2 table."""
    result = check_circle_packing.parse_number_string(raw_str)
    assert result == expected


@pytest.mark.parametrize(
    "raw_str",
    [
        "",
        "   ",
        " 1/2",
        "1/2 ",
        "1/2\n",
        "1 / 2",
        "\u0661/\u0662",
        "\uff11.\uff12",
        "1e-5",
        "2.5E+3",
        "nan",
        "NaN",
        "inf",
        "-infinity",
        "1/0",
        "1/00",
        "1/02",
        "1/-2",
        "1/2/3",
        "1.2.3",
        "1/2abc",
        "abc",
        "0." + ("1" * 99),
    ],
)
def test_spec_rejected_number_strings(raw_str: str) -> None:
    """Test all rejected number strings from spec section 5.2 table."""
    with pytest.raises(check_circle_packing.FormatError):
        check_circle_packing.parse_number_string(raw_str)


def test_format_error_missing_file() -> None:
    """Test format error when input file does not exist."""

    async def run() -> None:
        exit_code, lines = await check_circle_packing.check_construction_file(
            "nonexistent_file_abc123.json"
        )
        assert exit_code == 1
        assert lines == ["INVALID format_error: cannot read file"]

    run_async(run())


def test_format_error_utf8_bom(tmp_path: Path) -> None:
    """Test format error when file begins with UTF-8 byte order mark."""

    async def run() -> None:
        data = make_valid_grid_construction()
        bom_bytes = b"\xef\xbb\xbf" + json.dumps(data).encode("utf-8")
        json_path = tmp_path / "bom.json"
        await async_write_file(json_path, bom_bytes)

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: UTF-8 BOM detected")

    run_async(run())


def test_format_error_invalid_utf8(tmp_path: Path) -> None:
    """Test format error when file contains invalid UTF-8 bytes."""

    async def run() -> None:
        invalid_bytes = b'{"centers": \xff\xfe, "radii": []}'
        json_path = tmp_path / "invalid_utf8.json"
        await async_write_file(json_path, invalid_bytes)

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: invalid UTF-8")

    run_async(run())


def test_format_error_trailing_content(tmp_path: Path) -> None:
    """Test format error when file has trailing content after top-level object."""

    async def run() -> None:
        data = make_valid_grid_construction()
        content = json.dumps(data) + " extra_trailing_content"
        json_path = tmp_path / "trailing.json"
        await async_write_file(json_path, content.encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: trailing content")

    run_async(run())


def test_format_error_duplicate_keys(tmp_path: Path) -> None:
    """Test format error when JSON object contains duplicate keys."""

    async def run() -> None:
        raw_json = '{"centers": [], "centers": [], "radii": []}'
        json_path = tmp_path / "dup_keys.json"
        await async_write_file(json_path, raw_json.encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: duplicate key")

    run_async(run())


def test_format_error_top_level_not_object(tmp_path: Path) -> None:
    """Test format error when top-level JSON is a list instead of an object."""

    async def run() -> None:
        raw_json = "[]"
        json_path = tmp_path / "list_top.json"
        await async_write_file(json_path, raw_json.encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: top-level JSON value")

    run_async(run())


def test_format_error_missing_centers_key(tmp_path: Path) -> None:
    """Test format error when 'centers' key is missing."""

    async def run() -> None:
        raw_json = '{"radii": []}'
        json_path = tmp_path / "missing_centers.json"
        await async_write_file(json_path, raw_json.encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: object must contain")

    run_async(run())


def test_format_error_missing_radii_key(tmp_path: Path) -> None:
    """Test format error when 'radii' key is missing."""

    async def run() -> None:
        raw_json = '{"centers": []}'
        json_path = tmp_path / "missing_radii.json"
        await async_write_file(json_path, raw_json.encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: object must contain")

    run_async(run())


def test_format_error_extra_key(tmp_path: Path) -> None:
    """Test format error when an unexpected extra key is present."""

    async def run() -> None:
        data = make_valid_grid_construction()
        data["extra"] = 123
        json_path = tmp_path / "extra_key.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: object must contain")

    run_async(run())


def test_format_error_case_sensitive_keys(tmp_path: Path) -> None:
    """Test format error when keys have incorrect uppercase casing."""

    async def run() -> None:
        raw_json = '{"Centers": [], "radii": []}'
        json_path = tmp_path / "case_keys.json"
        await async_write_file(json_path, raw_json.encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: object must contain")

    run_async(run())


def test_format_error_centers_length_not_26(tmp_path: Path) -> None:
    """Test format error when 'centers' list length is not 26."""

    async def run() -> None:
        data = make_valid_grid_construction()
        data["centers"] = data["centers"][:25]
        json_path = tmp_path / "centers_25.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: 'centers' list must")

    run_async(run())


def test_format_error_radii_length_not_26(tmp_path: Path) -> None:
    """Test format error when 'radii' list length is not 26."""

    async def run() -> None:
        data = make_valid_grid_construction()
        data["radii"].append("1/12")
        json_path = tmp_path / "radii_27.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: 'radii' list must")

    run_async(run())


def test_format_error_coordinate_not_list(tmp_path: Path) -> None:
    """Test format error when a coordinate item in centers is not a list."""

    async def run() -> None:
        data = make_valid_grid_construction()
        data["centers"][0] = "1/2"  # type: ignore[assignment]
        json_path = tmp_path / "coord_not_list.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: item at index 0")

    run_async(run())


def test_format_error_coordinate_length_not_2(tmp_path: Path) -> None:
    """Test format error when a coordinate pair does not have length 2."""

    async def run() -> None:
        data = make_valid_grid_construction()
        data["centers"][0] = ["1/2", "1/2", "1/2"]
        json_path = tmp_path / "coord_len_3.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: coordinate pair")

    run_async(run())


def test_format_error_coordinate_bare_float(tmp_path: Path) -> None:
    """Test format error when coordinate is a bare JSON float."""

    async def run() -> None:
        data = make_valid_grid_construction()
        data["centers"][0] = [0.5, "1/2"]  # type: ignore[list-item]
        json_path = tmp_path / "bare_float.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: coordinates at index")

    run_async(run())


def test_format_error_coordinate_bare_int(tmp_path: Path) -> None:
    """Test format error when coordinate is a bare JSON integer."""

    async def run() -> None:
        data = make_valid_grid_construction()
        data["centers"][0] = [0, "1/2"]  # type: ignore[list-item]
        json_path = tmp_path / "bare_int.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: coordinates at index")

    run_async(run())


def test_format_error_coordinate_boolean(tmp_path: Path) -> None:
    """Test format error when coordinate is a boolean."""

    async def run() -> None:
        data = make_valid_grid_construction()
        data["centers"][0] = [True, "1/2"]  # type: ignore[list-item]
        json_path = tmp_path / "boolean_coord.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: coordinates at index")

    run_async(run())


def test_format_error_coordinate_null(tmp_path: Path) -> None:
    """Test format error when coordinate is JSON null."""

    async def run() -> None:
        data = make_valid_grid_construction()
        data["centers"][0] = [None, "1/2"]  # type: ignore[list-item]
        json_path = tmp_path / "null_coord.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: coordinates at index")

    run_async(run())


def test_format_error_radius_bare_float(tmp_path: Path) -> None:
    """Test format error when radius is a bare JSON float."""

    async def run() -> None:
        data = make_valid_grid_construction()
        data["radii"][0] = 0.1  # type: ignore[assignment]
        json_path = tmp_path / "radius_float.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: radius at index 0")

    run_async(run())


def test_format_error_radius_null(tmp_path: Path) -> None:
    """Test format error when radius is JSON null."""

    async def run() -> None:
        data = make_valid_grid_construction()
        data["radii"][0] = None  # type: ignore[assignment]
        json_path = tmp_path / "radius_null.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: radius at index 0")

    run_async(run())


def test_format_error_unicode_digits(tmp_path: Path) -> None:
    """Test format error when coordinate contains Unicode digits."""

    async def run() -> None:
        data = make_valid_grid_construction()
        data["centers"][0] = ["\u0661/\u0662", "1/2"]
        json_path = tmp_path / "unicode_digits.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: number string")

    run_async(run())


def test_format_error_control_characters(tmp_path: Path) -> None:
    """Test format error when number string contains control characters."""

    async def run() -> None:
        data = make_valid_grid_construction()
        data["centers"][0] = ["1/2\x00", "1/2"]
        json_path = tmp_path / "ctrl_char.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: number string contains")

    run_async(run())


def test_format_error_control_char_127(tmp_path: Path) -> None:
    """Test format error when number string contains DEL character (127)."""

    async def run() -> None:
        data = make_valid_grid_construction()
        data["radii"][0] = "1/2\x7f"
        json_path = tmp_path / "del_char.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: number string contains")

    run_async(run())


def test_format_error_number_len_101(tmp_path: Path) -> None:
    """Test format error when number string has length 101."""

    async def run() -> None:
        data = make_valid_grid_construction()
        data["radii"][0] = "0." + ("1" * 99)
        json_path = tmp_path / "len_101.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        exit_code, lines = await check_circle_packing.check_construction_file(
            str(json_path)
        )
        assert exit_code == 1
        assert lines[0].startswith("INVALID format_error: number string exceeds")

    run_async(run())

    script_path = str(Path(check_circle_packing.__file__).resolve())

    async def run() -> None:
        data = make_valid_grid_construction()
        json_path = tmp_path / "cli_valid.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            script_path,
            str(json_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, _ = await proc.communicate()
        assert proc.returncode == 0
        lines = stdout_bytes.decode("utf-8").splitlines()
        assert lines == ["VALID 13/6"]

    run_async(run())


def test_cli_execution_invalid(tmp_path: Path) -> None:
    """Test running check_circle_packing.py via subprocess CLI on invalid file."""
    script_path = str(Path(check_circle_packing.__file__).resolve())

    async def run() -> None:
        data = make_valid_grid_construction()
        data["radii"][0] = "0"
        json_path = tmp_path / "cli_invalid.json"
        await async_write_file(json_path, json.dumps(data).encode("utf-8"))

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            script_path,
            str(json_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, _ = await proc.communicate()
        assert proc.returncode == 1
        lines = stdout_bytes.decode("utf-8").splitlines()
        assert lines[0] == "INVALID"

    run_async(run())


def test_cli_execution_no_args() -> None:
    """Test running check_circle_packing.py via subprocess with no arguments."""
    script_path = str(Path(check_circle_packing.__file__).resolve())

    async def run() -> None:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, _ = await proc.communicate()
        assert proc.returncode == 1
        lines = stdout_bytes.decode("utf-8").splitlines()
        assert lines[0].startswith("INVALID format_error:")

    run_async(run())
