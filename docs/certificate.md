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
  "problem_spec_sha256": "5bb55661...afa7",
  "claim_type": "demonstration",
  "construction": {
    "centers": [["1/10", "1/10"], ...],
    "radii": ["1/10", ...]
  },
  "claimed_score": "38/15",
  "best_known": null,
  "best_known_tolerance": null,
  "run": null,
  "verifiers": {
    "exact_sha256": "86d806da...102c",
    "independent_sha256": "891b473a...3412"
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
| `claimed_score` | string | Exact score as an irreducible rational `p/q` in lowest terms (e.g. `"38/15"`). |
| `best_known` | object / null | Literature baseline: `{value, source_url, retrieved_date}` or `null`. |
| `best_known_tolerance` | string / null | Exact fraction tolerance in `[0, 1/1000]` for reproduction, or `null`. |
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
   - `best_known_tolerance` MUST be `null`.
   - `run` may be `null` or populate execution metadata.
   - Any mathematically valid score is permitted.

2. **`reproduction`**:
   - Represents reproducing a known published literature baseline within an approved tolerance.
   - `best_known` MUST NOT be `null` and must contain `{value, source_url, retrieved_date}` sourced from `baselines.json`.
   - `best_known_tolerance` is REQUIRED and MUST be an exact irreducible rational string in `[0, 1/1000]` (default `"0/1"`).
   - Exact arithmetic rule:
     $$\text{claimed\_score} \ge \text{best\_known.value} \times (1 - \text{tolerance})$$
   - `qed verify` prints the exact ratio $\text{claimed\_score} / \text{best\_known.value}$ to 10 decimal places.

3. **`record`**:
   - Claims a new state-of-the-art discovery exceeding literature best known.
   - `best_known` MUST NOT be `null` and must be sourced from a `human_verified` baseline in `baselines.json`.
   - `best_known_tolerance` MUST be `null`.
   - Exact arithmetic rule:
     - $\text{claimed\_score} - \text{best\_known.value} > 0$ strictly positive.
     - Furthermore, if $\text{best\_known.value}$ is expressed as a decimal string with $d$ fractional digits, the margin must satisfy:
       $$\text{claimed\_score} - \text{best\_known.value} \ge 10^{-d}$$
       (if $\text{best\_known.value}$ is expressed as an irreducible fraction $p/q$, strictly positive $> 0$ suffices).
   - Reason: published literature figures are often rounded approximations.

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

1. **Schema Validation**: Validates structure against Draft 2020-12 schema in `certificate_schema.json`.
2. **Certificate Hash**: Recomputes canonical hash and compares to `certificate_sha256`.
3. **Spec Integrity**: Recomputes SHA-256 of on-disk `spec.md` and verifies equality with `problem_spec_sha256`.
4. **Verifier Integrity**: Recomputes SHA-256 of `verifier_exact.py` and `check_circle_packing.py` and verifies equality with `verifiers.exact_sha256` and `verifiers.independent_sha256`.
5. **Exact Verification**: Executes `verifier_exact.py` in-process on the construction.
6. **Subprocess Independent Verification**: Writes construction to a temporary file and executes `check_circle_packing.py` in an isolated subprocess CLI.
7. **Score Parity**: Requires both verifiers return exit code 0 (`VALID`) with exact score matching `claimed_score`.
8. **Claim Gating**: Enforces `claim_type` requirements against `best_known` (tolerance bound for reproduction, margin resolution for record).

The tool outputs one line per check (`OK` or `FAILED: <reason>`), followed by `PASS` or `FAIL`, the exact score as `p/q`, and the score formatted to 40 decimal places.
Exit code is `0` on PASS, and `1` on FAIL.

---

## 6. Known Limits

The trust layer provides mathematical certainty within its defined scope, but has specific engineering boundaries:

(a) **Floating-Point Bridge**: The evolutionary engine produces floating-point coordinates and radii. These are bridged to exact rational arithmetic by `make_valid` (a rationalizer that snaps values to a fine dyadic/decimal grid and shrinks radii until certified). Shrinkage loss is tracked in `shrink_loss_exact`.  
(b) **Host-Colocated Cross-Verification**: Cross-checking is dual-implementation (`verifier_exact.py` and cleanroom `check_circle_packing.py`), but currently both checkers execute in Python on the same host operating system.  
(c) **Computational Scaling**: For circle packing with $N=26$, all-pairs quadratic checks ($N(N-1)/2 = 325$ pairs) take only milliseconds in pure integer arithmetic. Larger problem instances ($N \gg 100$) will require spatial indexing (quadtrees/grid hashing) or branch-and-bound / LP / MIP solvers to scale.  
(d) **Baseline Curation**: Literature baselines in `baselines.json` are curated and gated by human verification (`human_verified: true`). The trust gate verifies that a claim beats or matches the curated record; it is a governance gate, not a mathematical proof of the baseline itself.  
(e) **Cryptographic Signatures**: Certificates are cryptographically bound using SHA-256 canonical digest chaining, but are not yet signed with asymmetric public-key cryptography (no PKI or certificate authority infrastructure is implemented yet).  
(f) **Issuer Integrity**: Hash pinning detects edits made after issuing, not a dishonest or mistaken issuer.  
(g) **Runtime Dependency**: Both checkers are written in Python and run on CPython, so a shared CPython runtime bug would affect both.  
(h) **Provenance Independent of Mathematics**: The trust layer verifies mathematical correctness of the construction, not how it was found (a hand-crafted or benchmark-leaked construction would verify if valid).  
(i) **Fast-Loop Guidance**: Verification is exact, but floating-point evaluations in the fast search loop may misguide the search or drop near-valid candidates.
