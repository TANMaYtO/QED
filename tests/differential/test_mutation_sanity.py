"""Mutation testing sanity check for the differential testing harness.

Injects 6 deliberate bugs into temporary copies of verifier_exact:
1. Reject exact tangency (change >= to > or slack < 0 to slack <= 0).
2. Drop boundary check (remove top boundary containment check).
3. Evaluate circle overlap with float math instead of Fraction.
4. Reduce length cap from 100 to 99 characters.
5. Accept trailing newline in number strings.
6. Remove duplicate JSON key validation hook.

Verifies that the differential harness detects every single mutant.
"""

from __future__ import annotations

import json
import sys
from fractions import Fraction
from pathlib import Path
from types import ModuleType

from tests.differential.generators import (
    build_construction_dict,
    get_base_valid_26,
)
from tests.differential.harness import (
    compare_outputs,
    run_independent_bytes,
)

ORIGINAL_VERIFIER_PATH = (
    Path(__file__).parent.parent.parent
    / "src"
    / "qed"
    / "problems"
    / "circle_packing_n26"
    / "verifier_exact.py"
)


def load_mutated_module(mutated_code: str, module_name: str) -> ModuleType:
    """Compile and load a mutated verifier module registered in sys.modules."""
    module = ModuleType(module_name)
    module.__file__ = f"<{module_name}>"
    sys.modules[module_name] = module
    try:
        exec(mutated_code, module.__dict__)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def run_mutant_bytes(mutant: ModuleType, raw_bytes: bytes) -> tuple[int, list[str]]:
    """Execute the mutated verifier in-memory on raw byte content."""
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return 1, ["INVALID format_error: UTF-8 byte-order mark (BOM) is not allowed"]
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return 1, [
            f"INVALID format_error: Invalid UTF-8 encoding in construction file: {exc}"
        ]

    try:
        centers, radii = mutant.parse_construction_json(text)
        result = mutant.verify_packing_exact(centers, radii)
        out_lines = mutant.format_verification_output(result).splitlines()
        return (0 if result.ok else 1), out_lines
    except (ValueError, TypeError) as exc:
        return 1, [f"INVALID format_error: {exc}"]


def test_mutation_1_tangency_rejected() -> None:
    """Mutant 1: Change overlap condition so exact tangency (slack=0) is rejected."""
    src = ORIGINAL_VERIFIER_PATH.read_text(encoding="utf-8")
    target = "if overlap_slack < 0:"
    replacement = "if overlap_slack <= 0:"
    assert target in src, "Target string for mutation 1 not found"
    mutated_src = src.replace(target, replacement, 1)

    mutant = load_mutated_module(mutated_src, "mutant_tangency")

    # Pythagorean triple (3, 4, 5) exact tangency
    centers, radii = get_base_valid_26()
    c_list = list(centers)
    r_list = list(radii)
    c_list[0] = ("1/2", "1/2")
    r_list[0] = "3/20"
    c_list[1] = ("13/20", "7/10")
    r_list[1] = "1/10"
    for i in range(2, 26):
        c_list[i] = (f"{i}/30", "9/10")
        r_list[i] = "1/200"

    raw = json.dumps(build_construction_dict(c_list, r_list)).encode()
    res_mut = run_mutant_bytes(mutant, raw)
    res_ind = run_independent_bytes(raw)

    hard, _ = compare_outputs("mutant_tangency_test", raw, res_mut, res_ind)
    assert hard is not None, "Harness failed to detect Mutant 1 (tangency rejection)"
    assert hard.discrepancy_type in {"valid_class_mismatch", "exit_code_mismatch"}


def test_mutation_2_dropped_boundary_check() -> None:
    """Mutant 2: Drop the top boundary breach check."""
    src = ORIGINAL_VERIFIER_PATH.read_text(encoding="utf-8")
    target = "top_slack: Fraction = one - (y + r)"
    assert target in src, "Target string for mutation 2 not found"
    # Replace top boundary check with dummy true check
    replacement = "top_slack: Fraction = Fraction(1)"
    mutated_src = src.replace(target, replacement, 1)

    mutant = load_mutated_module(mutated_src, "mutant_top_boundary")

    # Circle exceeding top boundary: center y=1, r=1/12 -> y + r = 13/12 > 1
    centers, radii = get_base_valid_26()
    c_list = list(centers)
    c_list[0] = ("1/2", "1")
    raw = json.dumps(build_construction_dict(c_list, radii)).encode()

    res_mut = run_mutant_bytes(mutant, raw)
    res_ind = run_independent_bytes(raw)

    hard, _ = compare_outputs("mutant_boundary_test", raw, res_mut, res_ind)
    assert hard is not None, (
        "Harness failed to detect Mutant 2 (dropped boundary check)"
    )


def test_mutation_3_overlap_with_float_math() -> None:
    """Mutant 3: Evaluate circle overlap using float precision instead of Fraction."""
    src = ORIGINAL_VERIFIER_PATH.read_text(encoding="utf-8")
    target = "if overlap_slack < 0:"
    # Use 64-bit float comparison where tiny nudges (< 1e-16) round away
    replacement = "if float(dist_sq) < float(radii_sq):"
    assert target in src, "Target string for mutation 3 not found"
    mutated_src = src.replace(target, replacement, 1)

    mutant = load_mutated_module(mutated_src, "mutant_float_overlap")

    # Exact tangency + nudge of 10^-20 to radius: exact overlap, float missed
    centers, radii = get_base_valid_26()
    c_list = list(centers)
    r_list = list(radii)
    c_list[0] = ("1/2", "1/2")
    r_list[0] = "3/20"
    c_list[1] = ("13/20", "7/10")
    # Exact r2 + 10^-20 causes overlap in Fraction arithmetic, but rounds off in float64
    r2_frac = Fraction(1, 10) + Fraction(1, 10**20)
    r_list[1] = f"{r2_frac.numerator}/{r2_frac.denominator}"
    for i in range(2, 26):
        c_list[i] = (f"{i}/30", "9/10")
        r_list[i] = "1/200"

    raw = json.dumps(build_construction_dict(c_list, r_list)).encode()
    res_mut = run_mutant_bytes(mutant, raw)
    res_ind = run_independent_bytes(raw)

    hard, _ = compare_outputs("mutant_float_test", raw, res_mut, res_ind)
    assert hard is not None, (
        "Harness failed to detect Mutant 3 (float overlap evaluation)"
    )


def test_mutation_4_length_cap_99() -> None:
    """Mutant 4: Reduce length cap from 100 to 99 characters."""
    src = ORIGINAL_VERIFIER_PATH.read_text(encoding="utf-8")
    target = "if len(val) > 100:"
    replacement = "if len(val) > 99:"
    assert target in src, "Target string for mutation 4 not found"
    mutated_src = src.replace(target, replacement, 1)

    mutant = load_mutated_module(mutated_src, "mutant_cap_99")

    # Exactly 100 character number string: '1/' + 98 '9's
    centers, radii = get_base_valid_26()
    r_list = list(radii)
    r_list[0] = "1/" + ("9" * 98)
    raw = json.dumps(build_construction_dict(centers, r_list)).encode()

    res_mut = run_mutant_bytes(mutant, raw)
    res_ind = run_independent_bytes(raw)

    hard, _ = compare_outputs("mutant_cap_test", raw, res_mut, res_ind)
    assert hard is not None, "Harness failed to detect Mutant 4 (cap reduced to 99)"
    assert hard.discrepancy_type == "exit_code_mismatch"


def test_mutation_5_allow_trailing_newline() -> None:
    """Mutant 5: Allow trailing newlines in number strings."""
    src = ORIGINAL_VERIFIER_PATH.read_text(encoding="utf-8")
    target = "if not isinstance(val, str):"
    replacement = (
        'if isinstance(val, str) and val.endswith("\\n"):\n'
        "        val = val[:-1]\n"
        "    if not isinstance(val, str):"
    )
    assert target in src, "Target string for mutation 5 not found"
    mutated_src = src.replace(target, replacement, 1)

    mutant = load_mutated_module(mutated_src, "mutant_trailing_nl")

    centers, radii = get_base_valid_26()
    r_list = list(radii)
    r_list[0] = "1/12\n"
    raw = json.dumps(build_construction_dict(centers, r_list)).encode()

    res_mut = run_mutant_bytes(mutant, raw)
    res_ind = run_independent_bytes(raw)

    hard, _ = compare_outputs("mutant_nl_test", raw, res_mut, res_ind)
    assert hard is not None, (
        "Harness failed to detect Mutant 5 (trailing newline accepted)"
    )
    assert hard.discrepancy_type in {"valid_class_mismatch", "exit_code_mismatch"}


def test_mutation_6_remove_duplicate_key_check() -> None:
    """Mutant 6: Remove strict duplicate key validation hook."""
    src = ORIGINAL_VERIFIER_PATH.read_text(encoding="utf-8")
    target = "object_pairs_hook=_reject_duplicate_keys"
    assert target in src, "Target string for mutation 6 not found"
    mutated_src = src.replace(target, "object_pairs_hook=None", 1)

    mutant = load_mutated_module(mutated_src, "mutant_dup_keys")

    centers, radii = get_base_valid_26()
    c_json = json.dumps(build_construction_dict(centers, radii)["centers"])
    r_json = json.dumps(radii)
    dup_raw = (
        f'{{"centers": {c_json}, "centers": {c_json}, "radii": {r_json}}}'.encode()
    )

    res_mut = run_mutant_bytes(mutant, raw_bytes=dup_raw)
    res_ind = run_independent_bytes(dup_raw)

    hard, _ = compare_outputs("mutant_dup_key_test", dup_raw, res_mut, res_ind)
    assert hard is not None, (
        "Harness failed to detect Mutant 6 (duplicate keys allowed)"
    )
    assert hard.discrepancy_type == "exit_code_mismatch"
