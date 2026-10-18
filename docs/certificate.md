# QED Certificate Specification

Version: `1.0.0`  
Status: Standard  
Owner: QED Trust Layer

---

## 1. Overview

A **QED Certificate** is a self-contained, cryptographically secured document certifying a mathematical construction and its claimed score for an open optimization or discovery problem.

Trust is the product of QED. Therefore:
1. Every certificate binds the construction to the exact problem specification and to the two independent verifier implementations that validated it.
2. Every numerical quantity that gates a claim is an exact rational number (`fractions.Fraction` or integer). Floating-point numbers are strictly forbidden from all gating checks.
3. Every certificate must pass two independent checkers: the primary project verifier (`verifier_exact.py`) and the cleanroom independent verifier (`check_circle_packing.py`).

---

## 2. Certificate Fields & Structure

A valid QED certificate is a JSON document adhering to the JSON schema defined in [`src/qed/trust/certificate_schema.json`](../src/qed/trust/certificate_schema.json).

```json
{
  "schema_version": "1.0.0",
  "problem_id": "circle_packing_n26",
  "problem_spec_sha256": "43461234...5678",
  "claim_type": "demonstration",
  "construction": {
    "centers": [["1/12", "1/12"], ...],
    "radii": ["1/12", ...]
  },
  "claimed_score": "13/6",
  "best_known": null,
  "run": null,
  "verifiers": {
    "exact_sha256": "abcdef12...3456",
    "independent_sha256": "78901234...5678"
  },
  "created_at": "2026-10-18T20:00:00Z",
  "certificate_sha256": "fedcba98...7654"
}
```

### 2.1 Field Definitions

| Field | Type | Description |
|---|---|---|
| `schema_version` | string | Semantic version of the certificate schema (e.g. `"1.0.0"`). |
| `problem_id` | string | Unique problem identifier (e.g. `"circle_packing_n26"`). |
| `problem_spec_sha256` | string | Hex-encoded SHA-256 digest of the problem specification (`spec.md`). |
| `claim_type` | enum | Nature of claim: `'demonstration'`, `'reproduction'`, or `'record'`. |
| `construction` | object | The geometric construction object containing `"centers"` and `"radii"` formatted per `spec.md` Section 5. |
| `claimed_score` | string | Exact score as an irreducible rational `p/q` in lowest terms (e.g. `"13/6"`). |
| `best_known` | object / null | Literature baseline: `{value, source_url, retrieved_date}` or `null`. |
| `run` | object / null | Evolutionary provenance: `{run_id, engine, engine_version, model, iterations, best_fast_score, shrink_loss_exact}` or `null` for hand-crafted proofs. |
| `verifiers` | object | SHA-256 digests of the verifier source files: `{exact_sha256, independent_sha256}`. |
| `created_at` | string | UTC timestamp in ISO 8601 format (`YYYY-MM-DDTHH:MM:SSZ`). |
| `certificate_sha256` | string | Hex-encoded SHA-256 digest of the certificate's canonical JSON representation without this field. |

---

## 3. Claim Types and Policy Rules

QED enforces strict gating rules on `claim_type`:

1. **`demonstration`**:
   - Represents a baseline proof-of-concept, test fixture, or illustrative construction.
   - `best_known` MUST be `null`.
   - `run` may be `null` or populate execution metadata.

2. **`reproduction`**:
   - Represents reproducing a known published literature result or baseline.
   - `best_known` MUST NOT be `null` and must contain `{value, source_url, retrieved_date}`.
   - `claimed_score` is not required to exceed `best_known.value`, but must be mathematically valid.

3. **`record`**:
   - Claims a new state-of-the-art discovery exceeding best known literature.
   - `best_known` MUST NOT be `null`.
   - `claimed_score` MUST be strictly greater than `best_known.value` in exact rational arithmetic:
     $$\text{claimed\_score} - \text{best\_known.value} > 0$$
   - Any floating-point comparison is forbidden.

---

## 4. Canonical Hashing

To guarantee certificate immutability and detect any tampering:
1. All fields of the certificate dictionary are collected except `certificate_sha256`.
2. The dictionary is serialized to canonical JSON:
   - Keys sorted alphabetically (`sort_keys=True`).
   - Compact separators with no trailing or intra-key whitespace: `separators=(',', ':')`.
   - UTF-8 encoded with no byte order mark.
3. The SHA-256 hash of this byte sequence produces `certificate_sha256`.

---

## 5. Verification Protocol (`qed verify`)

When running `qed verify <cert.json>`, the trust layer performs the following checks in sequence:

1. **Schema Validation**: Validates structure against `certificate_schema.json`.
2. **Certificate Hash**: Recomputes canonical hash and compares to `certificate_sha256`.
3. **Spec Integrity**: Recomputes SHA-256 of on-disk `spec.md` and verifies equality with `problem_spec_sha256`.
4. **Verifier Integrity**: Recomputes SHA-256 of `verifier_exact.py` and `check_circle_packing.py` and verifies equality with `verifiers.exact_sha256` and `verifiers.independent_sha256`.
5. **Exact Verification**: Executes `verifier_exact.py` in-process on the construction.
6. **Subprocess Independent Verification**: Writes construction to a temporary file and executes `check_circle_packing.py` in an isolated subprocess CLI.
7. **Score Parity**: Requires both verifiers return exit code 0 (`VALID`) with exact score matching `claimed_score`.
8. **Claim Gating**: Enforces `claim_type` requirements against `best_known`.

The tool outputs one line per check (`OK` or `FAILED: <reason>`), followed by `PASS` or `FAIL`, the exact score as `p/q`, and the score formatted to 40 decimal places.
Exit code is `0` on PASS, and `1` on FAIL.
