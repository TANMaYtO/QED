# Differential Testing Report: Circle Packing Exact Verifiers

**Date:** 2026-10-18  
**Author:** QED Core Engineering Team  
**Subject:** Differential Verification Parity between `verifier_exact.py` and `check_circle_packing.py`  
**Status:** ACCEPTED (Zero disagreements across 21,500 test cases, 6/6 mutation bugs detected, 100% test coverage)

---

## 1. Executive Summary

This report documents the differential testing campaign conducted between two independent implementations of the exact verifier for the 26-circle packing problem (`circle_packing_n26`):

1. **`verifier_exact.py`** (`src/qed/problems/circle_packing_n26/verifier_exact.py`): The primary QED project verifier, using exact arithmetic via `fractions.Fraction` and integer square roots.
2. **`check_circle_packing.py`** (`tests/independent/check_circle_packing.py`): An independent reference checker written blind from `spec.md` alone in an isolated cleanroom session, implemented strictly using Python standard library primitives.

A deterministic differential testing harness was constructed in `tests/differential/` with a fixed random seed (`20261018`). The harness executed **21,500 test cases** across six adversarial generator suites (in-memory) and performed **300 subprocess CLI invocations**. 

Both checkers achieved **100% agreement** on exit codes, line-1 classification (`VALID <score>`, `INVALID`, or `INVALID format_error`), exact score representations as irreducible fractions `p/q`, and informational geometric violation sets.

In addition, a harness mutation test suite confirmed that 6 deliberate bugs injected into `verifier_exact.py` were all caught by the harness.

---

## 2. Provenance and Isolation

To prevent cognitive leakage and preserve adversarial integrity:
- `check_circle_packing.py` and its accompanying test suite `test_check.py` were authored in an independent workspace without access to `verifier_exact.py`, relying solely on the problem specification `spec.md`.
- All standard library and language features used by `check_circle_packing.py` are stdlib-only (`json`, `re`, `fractions.Fraction`, `math`, `sys`, `pathlib`).
- The files were copied into `tests/independent/` with a dedicated `README.md` documenting origin and constraints.
- No code logic from `verifier_exact.py` was introduced into `check_circle_packing.py`, and vice versa. Every patch applied to either verifier was strictly justified by direct reference to `spec.md` and recorded in `tests/independent/CHANGELOG.md`.

---

## 3. Specification Amendments

Prior to executing the 21,500-case harness, two ambiguities identified in `spec.md` were formalized:

### 3.1 Strict JSON Whitespace Rule (Section 5.1)
* **Spec text amendment:**
  > "Whitespace outside the top-level JSON value is strictly limited to the four ASCII whitespace characters: space (`0x20`), horizontal tab (`0x09`), line feed (`0x0A`), and carriage return (`0x0D`). Any other character before or after the JSON value (including Unicode Category Z characters like `\u00A0` NO-BREAK SPACE, `\u2003` EM SPACE, form feed `0x0C`, vertical tab `0x0B`, or byte order mark `\uFEFF`) is invalid and causes a format error. An empty file or a file containing only whitespace is invalid and causes a format error."
* **Rationale:** Python's `str.lstrip()` and `str.strip()` treat all Unicode Category Z space characters as whitespace. In contrast, standard JSON specification (RFC 8259 Section 2) strictly restricts JSON whitespace to `{0x20, 0x09, 0x0A, 0x0D}`. Without this rule, implementations using `str.strip()` would accept non-ASCII Unicode spaces outside the JSON document.

### 3.2 Slack Representation for Informational Violations (Section 5.4(e))
* **Spec text amendment:**
  > "The violation lines list each violated constraint instance with its type, 0-based circle indices, and slack value: `<violation_type>: indices=(<comma-separated indices>), slack=<exact rational>`. Slack values are formatted as irreducible fractions `p/q` with `q >= 1` (zero is formatted as `0/1`)."
* **Rationale:** Python's standard `str(Fraction(0))` outputs `"0"` rather than `"0/1"`, and integer fractions like `Fraction(-1)` format as `"-1"` rather than `"-1/1"`. Formatting slack as `f"{v.slack.numerator}/{v.slack.denominator}"` guarantees consistent `p/q` representations across both implementations.

---

## 4. Test Case Generation Breakdown

The generator suite (`tests/differential/generators.py`) produced **21,500 deterministic cases** across six distinct categories:

| Generator | Category | Case Count | Description |
|---|---|---|---|
| **A** | Exact Valid Packings | 3,500 | Regular grids (3x3 to 5x5 + remainder, varying radii), random rational radii that fit without overlap, Pythagorean distance triples (3-4-5, 5-12-13, 8-15-17 scaled) placing circles in exact boundary and mutual tangency. |
| **B** | Perturbations / Nudges | 4,000 | Systematic perturbations of valid packings from Generator A, shifting one center coordinate or radius by $+10^{-k}$ or $-10^{-k}$ for $k \in \{1, \dots, 40\}$. Spans macroscopic breaches down to deep sub-float precision ($10^{-40}$). |
| **C** | Number-String Fuzzing | 4,500 | Mutations of numeric strings using adversarial characters: signs (`+`, `-`), dots, slashes, non-ASCII Arabic-Indic digits (`\u0660-\u0669`), fullwidth digits (`\uff10-\uff19`), spaces, non-breaking spaces (`\u00a0`), null bytes (`\x00`), control characters (ASCII 1-31), DEL (`\x7f`), and leading zero denominators (`1/02`, `1/00`, `1/0`). |
| **D** | JSON-Level Mutations | 4,500 | Top-level whitespace with Unicode Category Z characters (`\u00a0`, `\u2003`), controls, BOM (`\xef\xbb\xbf`), invalid UTF-8 byte sequences (`\xff`, `\xc0\xaf`), trailing garbage, comments, trailing commas, duplicate keys with identical and distinct values, casing anomalies (`Centers`, `RADII`), non-string coordinates, non-list centers, wrong circle counts (0, 1, 25, 27 circles), and JSON primitives (`true`, `false`, `null`, `12345`). |
| **E** | Cap Boundaries & Big Ints | 3,000 | Number strings of length 99, 100, and 101 characters across decimals and fractions (e.g. `1/` followed by 97, 98, and 99 digits; `0.` followed by 97, 98, and 99 digits); fractions with denominators up to 100 digits; reducible large fractions (`11...1/22...2`). |
| **F** | Real Data & Nudges | 2,000 | Exact rational packing derived from the real best program discovered in `runs/circle_packing_n26_2b4ce989/openevolve/best` via `make_valid`, plus 1,999 rational perturbations ($10^{-1}$ to $10^{-30}$). |
| **Total** | | **21,500** | **All deterministic (RNG Seed: 20261018)** |

---

## 5. Disagreements Identified and Resolved

During harness construction and initial validation, two subtle contract disagreements were identified and resolved:

### Disagreement 1: Unicode Whitespace Rejection Outside Top-Level JSON
* **Input Example:**
  ```json
  \u00a0{"centers": [...], "radii": [...]}
  ```
* **Initial Outputs:**
  * `verifier_exact.py`: Rejected with exit code 1 (`INVALID format_error: ...`).
  * `check_circle_packing.py`: Returned exit code 0 (`VALID ...`), because `text.lstrip()` stripped `\u00a0`.
* **Resolution per `spec.md`:** Spec Section 5.1 was amended to strictly mandate ASCII whitespace `{0x20, 0x09, 0x0A, 0x0D}` outside JSON.
* **Fix Applied:** Modified `check_circle_packing.py` to scan for allowed ASCII whitespace without using `lstrip()`. Added entry to `tests/independent/CHANGELOG.md`.

### Disagreement 2: Slack Formatting for Integer Values
* **Input Example:**
  A circle with radius `0/1` violating the strict radius positivity condition $r_i > 0$.
* **Initial Outputs:**
  * `verifier_exact.py`: Printed `slack=0`.
  * `check_circle_packing.py`: Printed `slack=0/1`.
* **Resolution per `spec.md`:** Spec Section 5.4(e) requires slack values to print as `p/q` with $q \ge 1$, and zero specifically as `0/1`.
* **Fix Applied:** In `verifier_exact.py`, updated slack formatting in `format_verification_output` from `v.slack` to `f"{v.slack.numerator}/{v.slack.denominator}"`.

### Fuzzing & Stress Testing Outcome
Following the above two contract resolutions, the harness evaluated all **21,500 cases** with:
* **0 hard disagreements** (exit codes and first-line classes matched exactly).
* **0 score disagreements** (exact score strings matched character-for-character).
* **0 soft disagreements** (informational violation sets on invalid cases matched identically).
* **0 CLI subprocess sample errors** across 300 sampled cases.

---

## 6. Harness Mutation Testing (Sanity Check)

To ensure the differential harness actively detects defects rather than reporting false negatives, six deliberate bugs were injected into temporary mutant copies of `verifier_exact.py` via `tests/differential/test_mutation_sanity.py`:

| Mutant | Injected Bug | Target Behavior | Result / Detection Class |
|---|---|---|---|
| **Mutant 1** | Change `overlap_slack < 0` to `overlap_slack <= 0` | Rejects exact circle-circle tangency (Pythagorean 3-4-5 contact) | **CAUGHT**: `valid_class_mismatch` (Mutant reported `INVALID`, reference reported `VALID 13/6`) |
| **Mutant 2** | Omit top boundary breach check (`y + r <= 1`) | Accepts circles that breach the top of the unit square | **CAUGHT**: `exit_code_mismatch` (Mutant reported exit code 0, reference reported exit code 1) |
| **Mutant 3** | Replace `Fraction` overlap math with `float64` comparison | Misses overlap violations when radii are nudged by $10^{-20}$ | **CAUGHT**: `valid_class_mismatch` (Float math rounded away $10^{-20}$, mutant reported `VALID`, reference reported `INVALID`) |
| **Mutant 4** | Lower character cap from 100 to 99 chars | Rejects valid 100-character numeric strings | **CAUGHT**: `exit_code_mismatch` (Mutant reported exit code 1 `INVALID format_error`, reference reported exit code 0 `VALID`) |
| **Mutant 5** | Accept trailing newline in numeric strings (`1/12\n`) | Strips newline and allows control character `0x0A` | **CAUGHT**: `valid_class_mismatch` (Mutant accepted string, reference rejected as control char `0x0A`) |
| **Mutant 6** | Remove strict duplicate key hook (`object_pairs_hook=None`) | Silently accepts duplicate keys in JSON object | **CAUGHT**: `exit_code_mismatch` (Mutant accepted JSON, reference rejected duplicate keys) |

**Mutation Test Summary:** 6 of 6 mutants (100%) were detected and caught by the harness.

---

## 7. Verification Evidence and Command Outputs

### 7.1 Full Differential Test Suite
```powershell
.venv\Scripts\pytest -q tests/differential/test_differential.py
```
**Output:**
```
....                                                                     [100%]
4 passed in 58.12s
```

### 7.2 Mutation Sanity Test Suite
```powershell
.venv\Scripts\pytest -q tests/differential/test_mutation_sanity.py
```
**Output:**
```
......                                                                   [100%]
6 passed in 1.84s
```

### 7.3 Differential Regressions Suite
```powershell
.venv\Scripts\pytest -q tests/differential/regressions/test_regressions.py
```
**Output:**
```
.........                                                                [100%]
9 passed in 3.11s
```

### 7.4 Verifier Exact 100% Test Coverage
```powershell
.venv\Scripts\pytest --cov=qed.problems.circle_packing_n26.verifier_exact --cov-report=term-missing tests/test_verifier_exact.py
```
**Output:**
```
...............................................                          [100%]
=============================== tests coverage ================================
______________ coverage: platform win32, python 3.12.10-final-0 _______________

Name                                                    Stmts   Miss  Cover   Missing
-------------------------------------------------------------------------------------
src\qed\problems\circle_packing_n26\verifier_exact.py     268      0   100%
-------------------------------------------------------------------------------------
TOTAL                                                     268      0   100%
47 passed in 3.87s
```

### 7.5 Repository-Wide Lint and Formatting
```powershell
.venv\Scripts\ruff check . ; .venv\Scripts\ruff format --check .
```
**Output:**
```
All checks passed!
31 files already formatted
```

### 7.6 Full Repository Test Suite
```powershell
.venv\Scripts\pytest -q
```
**Output:**
```
........................................................................ [ 46%]
........................................................................ [ 93%]
..........                                                               [100%]
154 passed in 78.43s
```

---

## 8. Conclusion and Next Steps

The exact rational verifier for `circle_packing_n26` is now hardened through blind cross-implementation differential testing. Both `verifier_exact.py` and `check_circle_packing.py` are mathematically in sync across all edge cases, numerical boundaries, and format specifications.

**Suggested Next Step:** Integrate `verifier_exact.py` directly into the evaluation pipeline post-evolution to gate promotion claims for circle packing candidate programs.
