"""Regression tests for edge cases and contract nuances in differential verification.

Validates that verifier_exact and check_circle_packing behave identically on
boundary conditions, Unicode whitespace, slack formatting, tangencies, and caps.
"""

from __future__ import annotations

import json
from fractions import Fraction

from tests.differential.generators import (
    build_construction_dict,
    get_base_valid_26,
    make_valid,
)
from tests.differential.harness import (
    compare_outputs,
    run_independent_bytes,
    run_verifier_exact_bytes,
)


def run_both_and_compare(case_id: str, raw_bytes: bytes) -> tuple[int, list[str]]:
    """Execute both checkers on raw_bytes and assert full output parity."""
    res_exact = run_verifier_exact_bytes(raw_bytes)
    res_indep = run_independent_bytes(raw_bytes)

    hard, soft = compare_outputs(case_id, raw_bytes, res_exact, res_indep)
    assert hard is None, f"Hard disagreement on {case_id}: {hard}"
    assert soft is None, f"Soft disagreement on {case_id}: {soft}"
    return res_exact


def test_regression_unicode_whitespace_outside_json() -> None:
    """Test rejection of non-ASCII Category Z whitespace outside top-level JSON."""
    centers, radii = get_base_valid_26()
    valid_json = json.dumps(build_construction_dict(centers, radii))

    # ASCII whitespaces should both succeed
    ascii_padded = f"  \t\r\n{valid_json}\n\t  ".encode()
    code, lines = run_both_and_compare("ascii_ws", ascii_padded)
    assert code == 0
    assert lines[0].startswith("VALID")

    # Unicode NO-BREAK SPACE (\u00a0) outside JSON must be rejected as format error
    nbsp_padded = f"\u00a0{valid_json}".encode()
    code, lines = run_both_and_compare("unicode_nbsp_outside", nbsp_padded)
    assert code == 1
    assert lines[0].startswith("INVALID format_error")

    # Unicode EM SPACE (\u2003) outside JSON must be rejected as format error
    em_padded = f"{valid_json}\u2003".encode()
    code, lines = run_both_and_compare("unicode_em_outside", em_padded)
    assert code == 1
    assert lines[0].startswith("INVALID format_error")


def test_regression_slack_formatting() -> None:
    """Test informational slack formatting as p/q in lowest terms with zero as 0/1."""
    centers, radii = get_base_valid_26()
    # Set radius 0 at index 5 -> non_positive_radius with radius=0 -> slack=0/1
    radii_zero = list(radii)
    radii_zero[5] = "0/1"
    raw_zero = json.dumps(build_construction_dict(centers, radii_zero)).encode("utf-8")
    code, lines = run_both_and_compare("slack_zero", raw_zero)
    assert code == 1
    assert lines[0] == "INVALID"
    assert any("non_positive_radius: indices=(5,), slack=0/1" in line for line in lines)

    # Set negative radius -1/1 at index 3 -> slack=-1/1
    radii_neg = list(radii)
    radii_neg[3] = "-1/1"
    raw_neg = json.dumps(build_construction_dict(centers, radii_neg)).encode("utf-8")
    code, lines = run_both_and_compare("slack_neg_int", raw_neg)
    assert code == 1
    assert lines[0] == "INVALID"
    assert any(
        "non_positive_radius: indices=(3,), slack=-1/1" in line for line in lines
    )


def test_regression_exact_tangencies() -> None:
    """Test exact circle-circle and circle-boundary tangency."""
    centers, radii = get_base_valid_26()
    # Circle 0 at (1/12, 1/12) with r=1/12 exactly touches boundary x=0 and y=0
    centers_t = list(centers)
    radii_t = list(radii)
    centers_t[0] = ("1/12", "1/12")
    radii_t[0] = "1/12"
    # Circle 1 and Circle 2 touching via Pythagorean triple (3, 4, 5)/20:
    # Center 1 at (1/2, 1/2), r1 = 3/20
    # Center 2 at (1/2 + 3/20, 1/2 + 4/20) = (13/20, 7/10), r2 = 2/20 = 1/10
    # Distance = sqrt((3/20)^2 + (4/20)^2) = 5/20 = 1/4 = r1 + r2
    centers_t[1] = ("1/2", "1/2")
    radii_t[1] = "3/20"
    centers_t[2] = ("13/20", "7/10")
    radii_t[2] = "1/10"

    # Make the rest of circles tiny and separated along y=9/10
    for i in range(3, 26):
        centers_t[i] = (f"{i - 2}/25", "9/10")
        radii_t[i] = "1/200"

    raw = json.dumps(build_construction_dict(centers_t, radii_t)).encode("utf-8")
    code, lines = run_both_and_compare("exact_tangencies", raw)
    assert code == 0
    assert lines[0].startswith("VALID")


def test_regression_denominator_leading_zeros() -> None:
    """Test that denominators with leading zeros (e.g. 1/02, 1/00, 1/0) are rejected."""
    centers, radii = get_base_valid_26()

    for bad_den in ["1/02", "1/00", "1/0", "1/0005"]:
        radii_bad = list(radii)
        radii_bad[0] = bad_den
        raw = json.dumps(build_construction_dict(centers, radii_bad)).encode("utf-8")
        code, lines = run_both_and_compare(f"den_{bad_den}", raw)
        assert code == 1
        assert lines[0].startswith("INVALID format_error")


def test_regression_length_cap_boundaries() -> None:
    """Test length cap boundary at exactly 100 characters vs 101 characters."""
    centers, radii = get_base_valid_26()

    # Fraction length 100: "1/" + 98 digits -> accepted
    len100_frac = "1/" + ("9" * 98)
    radii_100 = list(radii)
    radii_100[0] = len100_frac
    raw_100 = json.dumps(build_construction_dict(centers, radii_100)).encode("utf-8")
    code, lines = run_both_and_compare("len100_frac", raw_100)
    assert code == 0
    assert lines[0].startswith("VALID")

    # Fraction length 101: "1/" + 99 digits -> rejected
    len101_frac = "1/" + ("9" * 99)
    radii_101 = list(radii)
    radii_101[0] = len101_frac
    raw_101 = json.dumps(build_construction_dict(centers, radii_101)).encode("utf-8")
    code, lines = run_both_and_compare("len101_frac", raw_101)
    assert code == 1
    assert lines[0].startswith("INVALID format_error")


def test_regression_trailing_newline_and_controls() -> None:
    """Test rejection of trailing newlines or control chars in number strings."""
    centers, radii = get_base_valid_26()

    radii_nl = list(radii)
    radii_nl[0] = "1/12\n"
    raw_nl = json.dumps(build_construction_dict(centers, radii_nl)).encode("utf-8")
    code, lines = run_both_and_compare("nl_in_num", raw_nl)
    assert code == 1
    assert lines[0].startswith("INVALID format_error")

    radii_ctrl = list(radii)
    radii_ctrl[0] = "1/12\x00"
    raw_ctrl = json.dumps(build_construction_dict(centers, radii_ctrl)).encode("utf-8")
    code, lines = run_both_and_compare("null_in_num", raw_ctrl)
    assert code == 1
    assert lines[0].startswith("INVALID format_error")


def test_regression_duplicate_json_keys() -> None:
    """Test rejection of duplicate keys in top-level JSON object."""
    centers, radii = get_base_valid_26()
    c_json = json.dumps(build_construction_dict(centers, radii)["centers"])
    r_json = json.dumps(radii)

    dup_raw = (
        f'{{"centers": {c_json}, "centers": {c_json}, "radii": {r_json}}}'.encode()
    )
    code, lines = run_both_and_compare("dup_keys", dup_raw)
    assert code == 1
    assert lines[0].startswith("INVALID format_error")


def test_regression_bom_and_empty_file() -> None:
    """Test rejection of UTF-8 byte order mark and empty or whitespace-only files."""
    centers, radii = get_base_valid_26()
    valid_bytes = json.dumps(build_construction_dict(centers, radii)).encode("utf-8")

    bom_bytes = b"\xef\xbb\xbf" + valid_bytes
    code, lines = run_both_and_compare("bom_rejection", bom_bytes)
    assert code == 1
    assert lines[0].startswith("INVALID format_error")

    code, lines = run_both_and_compare("empty_file", b"")
    assert code == 1
    assert lines[0].startswith("INVALID format_error")

    code, lines = run_both_and_compare("ws_only_file", b"   \t\r\n  ")
    assert code == 1
    assert lines[0].startswith("INVALID format_error")


def test_regression_real_candidate_packing() -> None:
    """Test exact verification of candidate program from circle_packing_n26_2b4ce989."""
    centers, radii = get_base_valid_26()
    # Perturb with tiny exact rational offset
    eps = Fraction(1, 10**25)
    r_perturbed = list(radii)
    r_perturbed[0] = f"{Fraction(radii[0]) - eps}"

    valid_res = make_valid(
        [[float(Fraction(c[0])), float(Fraction(c[1]))] for c in centers],
        [float(Fraction(r)) for r in r_perturbed],
    )
    real_centers = [(c[0], c[1]) for c in valid_res.exact_centers]
    real_radii = list(valid_res.exact_radii)

    raw_real = json.dumps(build_construction_dict(real_centers, real_radii)).encode(
        "utf-8"
    )
    code, lines = run_both_and_compare("real_candidate", raw_real)
    assert code == 0
    assert lines[0].startswith("VALID")
