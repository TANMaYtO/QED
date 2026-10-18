"""Deterministic test case generators for circle packing differential testing.

Generates 20,000+ exact test cases across categories A to F using fixed random seeds.
"""

from __future__ import annotations

import json
import random
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

from qed.problems.circle_packing_n26.verifier_exact import make_valid

RNG_SEED = 42


def get_base_valid_26() -> tuple[list[tuple[str, str]], list[str]]:
    """Return a baseline mathematically valid 26-circle packing."""
    centers: list[tuple[str, str]] = []
    radii: list[str] = []
    # 5x5 grid of circles with radius 1/26
    for i in range(5):
        for j in range(5):
            centers.append((f"{2 * i + 1}/10", f"{2 * j + 1}/10"))
            radii.append("1/26")
    # 26th circle in interstitial space at (1/5, 1/5) with radius 1/26
    centers.append(("1/5", "1/5"))
    radii.append("1/26")
    return centers, radii


def build_construction_dict(
    centers: list[tuple[str, str]] | list[list[Any]],
    radii: list[str] | list[Any],
) -> dict[str, Any]:
    """Assemble centers and radii into standard construction dictionary."""
    return {
        "centers": [[c[0], c[1]] for c in centers],
        "radii": list(radii),
    }


def generate_cases_a(count: int = 3500) -> list[tuple[str, bytes]]:
    """Generator A: Exact valid packings.

    Grids, random rational radii within bounds, Pythagorean distance triples,
    and exact boundary tangencies.
    """
    rng = random.Random(RNG_SEED + 1)
    cases: list[tuple[str, bytes]] = []

    # 1. Grid variations with different rational radii
    for idx in range(1000):
        centers: list[tuple[str, str]] = []
        radii: list[str] = []
        # Choose a common safe radius between 1/100 and 1/26
        den = rng.randint(26, 120)
        num = 1
        r_str = f"{num}/{den}"
        for i in range(5):
            for j in range(5):
                centers.append((f"{2 * i + 1}/10", f"{2 * j + 1}/10"))
                radii.append(r_str)
        centers.append(("1/5", "1/5"))
        radii.append(r_str)
        data = build_construction_dict(centers, radii)
        raw = json.dumps(data).encode("utf-8")
        cases.append((f"A_grid_{idx}", raw))

    # 2. Exact boundary tangency packings
    for idx in range(1200):
        centers, radii = get_base_valid_26()
        # Make circle 0 touch left boundary: x = r
        r_val = f"1/{rng.randint(30, 80)}"
        r_frac = Fraction(r_val)
        centers[0] = (f"{r_frac.numerator}/{r_frac.denominator}", "1/2")
        radii[0] = r_val
        # Make circle 1 touch right boundary: x = 1 - r
        r_val2 = f"1/{rng.randint(30, 80)}"
        r_frac2 = Fraction(r_val2)
        x_right = Fraction(1) - r_frac2
        centers[1] = (f"{x_right.numerator}/{x_right.denominator}", "1/2")
        radii[1] = r_val2
        # Make circle 2 touch bottom boundary: y = r
        centers[2] = ("1/2", f"{r_frac.numerator}/{r_frac.denominator}")
        radii[2] = r_val
        # Make circle 3 touch top boundary: y = 1 - r
        y_top = Fraction(1) - r_frac2
        centers[3] = ("1/2", f"{y_top.numerator}/{y_top.denominator}")
        radii[3] = r_val2
        data = build_construction_dict(centers, radii)
        cases.append((f"A_tangency_{idx}", json.dumps(data).encode("utf-8")))

    # 3. Exact circle-circle tangency using Pythagorean distance triples
    # Triples: (3, 4, 5) with scale M=100 -> dx=3/100, dy=4/100, dist=5/100
    # Touch when r1 + r2 = 5/100 (e.g. r1=2/100, r2=3/100)
    for idx in range(1300):
        centers, radii = get_base_valid_26()
        m_scale = rng.randint(50, 100)
        # Circle 0 at (1/4, 1/4), Circle 1 at (1/4 + 3/m_scale, 1/4 + 4/m_scale)
        c0_x, c0_y = Fraction(1, 4), Fraction(1, 4)
        c1_x = c0_x + Fraction(3, m_scale)
        c1_y = c0_y + Fraction(4, m_scale)
        # Total distance is 5/m_scale. Split into r0 = 2/m_scale, r1 = 3/m_scale
        r0 = Fraction(2, m_scale)
        r1 = Fraction(3, m_scale)
        centers[0] = (
            f"{c0_x.numerator}/{c0_x.denominator}",
            f"{c0_y.numerator}/{c0_y.denominator}",
        )
        centers[1] = (
            f"{c1_x.numerator}/{c1_x.denominator}",
            f"{c1_y.numerator}/{c1_y.denominator}",
        )
        radii[0] = f"{r0.numerator}/{r0.denominator}"
        radii[1] = f"{r1.numerator}/{r1.denominator}"
        # Shrink others to 1/200 so no overlaps
        for k in range(2, 26):
            radii[k] = "1/200"
        data = build_construction_dict(centers, radii)
        cases.append((f"A_pythagoras_{idx}", json.dumps(data).encode("utf-8")))

    return cases[:count]


def generate_cases_b(count: int = 4000) -> list[tuple[str, bytes]]:
    """Generator B: Nudges (10^-k for k=1..40 across boundaries and overlaps)."""
    cases: list[tuple[str, bytes]] = []
    case_idx = 0

    for k in range(1, 41):
        eps = Fraction(1, 10**k)
        for sub in range(25):
            centers, radii = get_base_valid_26()
            r_frac = Fraction(radii[0])

            # 1. Left boundary: inside (x = r + eps) and outside (x = r - eps)
            x_in = r_frac + eps
            centers[0] = (f"{x_in.numerator}/{x_in.denominator}", "1/2")
            cases.append(
                (
                    f"B_left_in_k{k}_{sub}",
                    json.dumps(build_construction_dict(centers, radii)).encode("utf-8"),
                )
            )
            case_idx += 1

            x_out = r_frac - eps
            centers[0] = (f"{x_out.numerator}/{x_out.denominator}", "1/2")
            cases.append(
                (
                    f"B_left_out_k{k}_{sub}",
                    json.dumps(build_construction_dict(centers, radii)).encode("utf-8"),
                )
            )
            case_idx += 1

            # 2. Right boundary: inside and outside
            x_r_in = Fraction(1) - r_frac - eps
            centers[0] = (f"{x_r_in.numerator}/{x_r_in.denominator}", "1/2")
            cases.append(
                (
                    f"B_right_in_k{k}_{sub}",
                    json.dumps(build_construction_dict(centers, radii)).encode("utf-8"),
                )
            )
            case_idx += 1

            x_r_out = Fraction(1) - r_frac + eps
            centers[0] = (f"{x_r_out.numerator}/{x_r_out.denominator}", "1/2")
            cases.append(
                (
                    f"B_right_out_k{k}_{sub}",
                    json.dumps(build_construction_dict(centers, radii)).encode("utf-8"),
                )
            )
            case_idx += 1

            # 3. Bottom boundary: inside and outside
            y_b_in = r_frac + eps
            centers[0] = ("1/2", f"{y_b_in.numerator}/{y_b_in.denominator}")
            cases.append(
                (
                    f"B_bottom_in_k{k}_{sub}",
                    json.dumps(build_construction_dict(centers, radii)).encode("utf-8"),
                )
            )
            case_idx += 1

            y_b_out = r_frac - eps
            centers[0] = ("1/2", f"{y_b_out.numerator}/{y_b_out.denominator}")
            cases.append(
                (
                    f"B_bottom_out_k{k}_{sub}",
                    json.dumps(build_construction_dict(centers, radii)).encode("utf-8"),
                )
            )
            case_idx += 1

            # 4. Top boundary: inside and outside
            y_t_in = Fraction(1) - r_frac - eps
            centers[0] = ("1/2", f"{y_t_in.numerator}/{y_t_in.denominator}")
            cases.append(
                (
                    f"B_top_in_k{k}_{sub}",
                    json.dumps(build_construction_dict(centers, radii)).encode("utf-8"),
                )
            )
            case_idx += 1

            y_t_out = Fraction(1) - r_frac + eps
            centers[0] = ("1/2", f"{y_t_out.numerator}/{y_t_out.denominator}")
            cases.append(
                (
                    f"B_top_out_k{k}_{sub}",
                    json.dumps(build_construction_dict(centers, radii)).encode("utf-8"),
                )
            )
            case_idx += 1

            # 5. Overlap tangency: distance is 5/50 = 1/10
            # Centers at (1/4, 1/4) and (1/4 + 3/50, 1/4 + 4/50)
            c0 = (Fraction(1, 4), Fraction(1, 4))
            c1 = (c0[0] + Fraction(3, 50), c0[1] + Fraction(4, 50))
            centers[0] = (
                f"{c0[0].numerator}/{c0[0].denominator}",
                f"{c0[1].numerator}/{c0[1].denominator}",
            )
            centers[1] = (
                f"{c1[0].numerator}/{c1[0].denominator}",
                f"{c1[1].numerator}/{c1[1].denominator}",
            )
            # Tangent sum = 1/10
            # Nudge separated: r0 + r1 = 1/10 - eps
            r0 = Fraction(1, 20)
            r1_sep = Fraction(1, 20) - eps
            radii[0] = f"{r0.numerator}/{r0.denominator}"
            radii[1] = f"{r1_sep.numerator}/{r1_sep.denominator}"
            cases.append(
                (
                    f"B_overlap_sep_k{k}_{sub}",
                    json.dumps(build_construction_dict(centers, radii)).encode("utf-8"),
                )
            )
            case_idx += 1

            # Nudge overlap: r0 + r1 = 1/10 + eps
            r1_ovp = Fraction(1, 20) + eps
            radii[1] = f"{r1_ovp.numerator}/{r1_ovp.denominator}"
            cases.append(
                (
                    f"B_overlap_ovp_k{k}_{sub}",
                    json.dumps(build_construction_dict(centers, radii)).encode("utf-8"),
                )
            )
            case_idx += 1

            if len(cases) >= count:
                return cases[:count]

    return cases[:count]


def generate_cases_c(count: int = 4500) -> list[tuple[str, bytes]]:
    """Generator C: Number-string fuzzing (alphabet mutations, inserts, deletes)."""
    rng = random.Random(RNG_SEED + 3)
    fuzz_alphabet = list("0123456789+-./eE \t\nnaif\u0661\uff11\x00\x7f")
    valid_bases = [
        "1/2",
        "0.5",
        "10/3",
        "0",
        "1",
        ".5",
        "5.",
        "-0.125",
        "+7",
        "26/1",
        "0/1",
        "+0.0",
        "123/456",
        "0.0001",
        "99.",
        ".001",
        "+1/2",
    ]
    cases: list[tuple[str, bytes]] = []

    for idx in range(count):
        centers, radii = get_base_valid_26()
        mutation_mode = idx % 3

        if mutation_mode == 0:
            # Random string from alphabet
            length = rng.randint(1, 20)
            mutated = "".join(rng.choice(fuzz_alphabet) for _ in range(length))
        elif mutation_mode == 1:
            # Single-character insertion or replacement on valid base
            base = rng.choice(valid_bases)
            char = rng.choice(fuzz_alphabet)
            pos = rng.randint(0, len(base))
            if rng.random() < 0.5:
                # Insert
                mutated = base[:pos] + char + base[pos:]
            else:
                # Replace
                if len(base) > 0:
                    replace_pos = rng.randint(0, len(base) - 1)
                    mutated = base[:replace_pos] + char + base[replace_pos + 1 :]
                else:
                    mutated = char
        else:
            # Single-character deletion
            base = rng.choice(valid_bases)
            if len(base) > 1:
                del_pos = rng.randint(0, len(base) - 1)
                mutated = base[:del_pos] + base[del_pos + 1 :]
            else:
                mutated = ""

        # Randomly inject into center or radius
        if rng.random() < 0.5:
            c_idx = rng.randint(0, 25)
            coord_idx = rng.randint(0, 1)
            pair = list(centers[c_idx])
            pair[coord_idx] = mutated
            centers[c_idx] = (pair[0], pair[1])
        else:
            r_idx = rng.randint(0, 25)
            radii[r_idx] = mutated

        data = build_construction_dict(centers, radii)
        try:
            raw = json.dumps(data).encode("utf-8")
        except (UnicodeEncodeError, TypeError):
            raw = b'{"centers": [["invalid", "1/2"]], "radii": []}'
        cases.append((f"C_fuzz_{idx}", raw))

    return cases[:count]


def generate_cases_d(count: int = 4500) -> list[tuple[str, bytes]]:
    """Generator D: JSON-level mutations (Unicode category Z, controls, syntax)."""
    rng = random.Random(RNG_SEED + 4)
    unicode_z_chars = [
        "\u0020",
        "\u00a0",
        "\u1680",
        "\u2000",
        "\u2001",
        "\u2002",
        "\u2003",
        "\u2004",
        "\u2005",
        "\u2006",
        "\u2007",
        "\u2008",
        "\u2009",
        "\u200a",
        "\u2028",
        "\u2029",
        "\u202f",
        "\u205f",
        "\u3000",
    ]
    controls = [chr(i) for i in range(32)] + [chr(127)]
    cases: list[tuple[str, bytes]] = []

    # Baseline valid JSON string
    centers, radii = get_base_valid_26()
    valid_json = json.dumps(build_construction_dict(centers, radii))

    for idx in range(count):
        cat = idx % 12
        if cat == 0:
            # Category Z whitespace leading/trailing
            z_char = rng.choice(unicode_z_chars)
            mutated_str = (
                f"{z_char}{valid_json}" if idx % 2 == 0 else f"{valid_json}{z_char}"
            )
            raw = mutated_str.encode("utf-8")
        elif cat == 1:
            # Control characters leading/trailing
            c_char = rng.choice(controls)
            mutated_str = (
                f"{c_char}{valid_json}" if idx % 2 == 0 else f"{valid_json}{c_char}"
            )
            raw = mutated_str.encode("utf-8")
        elif cat == 2:
            # UTF-8 BOM
            raw = b"\xef\xbb\xbf" + valid_json.encode("utf-8")
        elif cat == 3:
            # Invalid UTF-8 bytes
            invalid_seqs = [
                b"\xff\xfe",
                b"\x80",
                b"\xc0\xaf",
                b"\xed\xa0\x80",
                b"\xf4\x90\x80\x80",
            ]
            raw = rng.choice(invalid_seqs) + valid_json.encode("utf-8")
        elif cat == 4:
            # Trailing garbage outside JSON
            garbage = rng.choice(
                [" extra", " null", " 123", " []", " \x00", " /* comment */"]
            )
            raw = f"{valid_json}{garbage}".encode()
        elif cat == 5:
            # Comments, trailing commas, single quotes
            variant = idx % 3
            if variant == 0:
                raw = f"// leading comment\n{valid_json}".encode()
            elif variant == 1:
                # Trailing comma in list
                raw = valid_json.replace('"radii": [', '"radii": [,').encode("utf-8")
            else:
                # Single quotes
                raw = valid_json.replace('"', "'").encode("utf-8")
        elif cat == 6:
            # Duplicate keys (identical vs different)
            c_raw = build_construction_dict(centers, radii)["centers"]
            c_json = json.dumps(c_raw)
            r_json = json.dumps(radii)
            if idx % 2 == 0:
                raw = (
                    f'{{"centers": {c_json}, "centers": {c_json}, "radii": {r_json}}}'
                ).encode()
            else:
                raw = (
                    f'{{"centers": {c_json}, "radii": {r_json}, "radii": []}}'
                ).encode()
        elif cat == 7:
            # Key case changes / extra keys / missing keys
            case_var = idx % 4
            if case_var == 0:
                raw = valid_json.replace('"centers"', '"Centers"').encode("utf-8")
            elif case_var == 1:
                raw = valid_json.replace('"radii"', '"RADII"').encode("utf-8")
            elif case_var == 2:
                # Extra key
                raw = valid_json.replace("{", '{"extra_key": 42, ', 1).encode("utf-8")
            else:
                # Missing key
                raw = json.dumps(
                    {"centers": build_construction_dict(centers, radii)["centers"]}
                ).encode("utf-8")
        elif cat == 8:
            # Wrong types (bare numbers, boolean, null, floats)
            type_var = idx % 4
            if type_var == 0:
                raw = b"12345"
            elif type_var == 1:
                raw = json.dumps({"centers": 123, "radii": 456}).encode("utf-8")
            elif type_var == 2:
                # Coordinates as floats
                raw = json.dumps(
                    {
                        "centers": [[0.5, 0.5] for _ in range(26)],
                        "radii": ["1/10" for _ in range(26)],
                    }
                ).encode("utf-8")
            else:
                raw = json.dumps(
                    {
                        "centers": [[None, None] for _ in range(26)],
                        "radii": ["1/10" for _ in range(26)],
                    }
                ).encode("utf-8")
        elif cat == 9:
            # Escaped digits, escaped control chars
            raw = valid_json.replace('"1/26"', r'"\u0031/\u0032\u0036"').encode("utf-8")
        elif cat == 10:
            # Lone surrogates / deep nesting
            if idx % 2 == 0:
                raw = b'{"centers": "\\ud800", "radii": []}'
            else:
                raw = b"[[[[[[[[[[[[[[[[[[[[{}]]]]]]]]]]]]]]]]]]]]"
        else:
            # Empty file / whitespace only
            ws_only = rng.choice(["", "   ", "\n\t\r", "  \n  \t  \r\n  "])
            raw = ws_only.encode("utf-8")

        cases.append((f"D_json_{idx}", raw))

    return cases[:count]


def generate_cases_e(count: int = 3000) -> list[tuple[str, bytes]]:
    """Generator E: Cap boundaries (lengths 99, 100, 101, and large denominators)."""
    rng = random.Random(RNG_SEED + 5)
    cases: list[tuple[str, bytes]] = []

    for idx in range(count):
        centers, radii = get_base_valid_26()
        cat = idx % 6

        if cat == 0:
            # Decimal string length 99, 100, 101
            target_len = rng.choice([99, 100, 101])
            num_str = "0." + "1" * (target_len - 2)
            assert len(num_str) == target_len
            radii[0] = num_str
        elif cat == 1:
            # Fraction string length 99, 100, 101
            target_len = rng.choice([99, 100, 101])
            den_len = target_len - 2  # '1/' + digits
            num_str = "1/" + "9" * den_len
            assert len(num_str) == target_len
            radii[0] = num_str
        elif cat == 2:
            # Denominators up to 100 digits
            digits = rng.randint(20, 98)
            num_str = "1/" + "1" + ("0" * digits)
            if len(num_str) <= 100:
                radii[0] = num_str
            else:
                radii[0] = "1/10"
        elif cat == 3:
            # Denominators with leading zeros (1/02, 1/00, 1/0)
            bad_den = rng.choice(["1/02", "1/00", "1/0", "1/00005", "1/010"])
            radii[0] = bad_den
        elif cat == 4:
            # Numerators with leading zeros (valid)
            valid_leading = rng.choice(["007", "000.123", "+001/2", "00/1", "+00.5"])
            radii[0] = valid_leading
        else:
            # Reducible large fractions
            d_len = rng.randint(10, 45)
            big_num = "1" * d_len
            big_den = "2" * d_len
            num_str = f"{big_num}/{big_den}"
            radii[0] = num_str

        raw = json.dumps(build_construction_dict(centers, radii)).encode("utf-8")
        cases.append((f"E_cap_{idx}", raw))

    return cases[:count]


def generate_cases_f(count: int = 2000) -> list[tuple[str, bytes]]:
    """Generator F: Real data from runs/circle_packing_n26_2b4ce989 plus nudges."""
    rng = random.Random(RNG_SEED + 6)
    cases: list[tuple[str, bytes]] = []

    # Import best program from runs directory
    best_prog_dir = (
        Path(__file__).parent.parent.parent
        / "runs"
        / "circle_packing_n26_2b4ce989"
        / "openevolve"
        / "best"
    )
    if str(best_prog_dir) not in sys.path:
        sys.path.insert(0, str(best_prog_dir))

    try:
        from best_program import run_packing  # type: ignore[import-not-found]

        c_float, r_float, _ = run_packing()
        valid_res = make_valid(c_float.tolist(), r_float.tolist())
        exact_centers = [(c[0], c[1]) for c in valid_res.exact_centers]
        exact_radii = list(valid_res.exact_radii)
    except Exception:
        # Fallback to base valid if best_program cannot be loaded
        exact_centers, exact_radii = get_base_valid_26()

    # 1. Unmodified exact valid real data
    cases.append(
        (
            "F_real_exact_baseline",
            json.dumps(build_construction_dict(exact_centers, exact_radii)).encode(
                "utf-8"
            ),
        )
    )

    # 2. Nudged versions of real data
    for idx in range(count - 1):
        c_copy = [list(c) for c in exact_centers]
        r_copy = list(exact_radii)

        circle_idx = rng.randint(0, 25)
        k = rng.randint(1, 30)
        eps = Fraction(1, 10**k)

        nudge_choice = rng.randint(0, 4)
        if nudge_choice == 0:
            # Nudge radius larger (likely overlap or boundary breach)
            orig_r = Fraction(r_copy[circle_idx])
            nudged = orig_r + eps
            r_copy[circle_idx] = f"{nudged.numerator}/{nudged.denominator}"
        elif nudge_choice == 1:
            # Nudge radius smaller (strictly valid)
            orig_r = Fraction(r_copy[circle_idx])
            nudged = max(Fraction(1, 1000), orig_r - eps)
            r_copy[circle_idx] = f"{nudged.numerator}/{nudged.denominator}"
        elif nudge_choice == 2:
            # Nudge x coordinate
            orig_x = Fraction(c_copy[circle_idx][0])
            nudged_x = orig_x + (eps if rng.random() < 0.5 else -eps)
            c_copy[circle_idx][0] = f"{nudged_x.numerator}/{nudged_x.denominator}"
        elif nudge_choice == 3:
            # Nudge y coordinate
            orig_y = Fraction(c_copy[circle_idx][1])
            nudged_y = orig_y + (eps if rng.random() < 0.5 else -eps)
            c_copy[circle_idx][1] = f"{nudged_y.numerator}/{nudged_y.denominator}"
        else:
            # Multiple circles slightly shrunk (valid)
            for j in range(26):
                if rng.random() < 0.3:
                    orig_r = Fraction(r_copy[j])
                    shrunk = max(
                        Fraction(1, 1000),
                        orig_r - Fraction(1, 10 ** rng.randint(6, 15)),
                    )
                    r_copy[j] = f"{shrunk.numerator}/{shrunk.denominator}"

        raw = json.dumps(build_construction_dict(c_copy, r_copy)).encode("utf-8")
        cases.append((f"F_real_nudge_{idx}", raw))

    return cases[:count]


def get_all_test_cases() -> tuple[list[tuple[str, bytes]], dict[str, int]]:
    """Generate all 20,000+ test cases across generators A through F."""
    cases_a = generate_cases_a(3500)
    cases_b = generate_cases_b(4000)
    cases_c = generate_cases_c(4500)
    cases_d = generate_cases_d(4500)
    cases_e = generate_cases_e(3000)
    cases_f = generate_cases_f(2000)

    counts = {
        "Generator A (Exact Valid Packings)": len(cases_a),
        "Generator B (Nudges)": len(cases_b),
        "Generator C (Number-String Fuzz)": len(cases_c),
        "Generator D (JSON-Level Mutations)": len(cases_d),
        "Generator E (Cap Boundaries)": len(cases_e),
        "Generator F (Real Data & Nudges)": len(cases_f),
    }

    all_cases = cases_a + cases_b + cases_c + cases_d + cases_e + cases_f
    return all_cases, counts
