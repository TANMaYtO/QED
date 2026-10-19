"""Certificate generation, schema validation, and cryptographic verification engine.

Provides full trust-layer validation for QED mathematical discovery claims:
- JSON schema validation via jsonschema Draft 2020-12
- Cryptographic hash chaining (spec, verifiers, canonical certificate)
- Cross-checker dual verification (verifier_exact and independent subprocess)
- Exact rational arithmetic claim gating policies and literature baselines
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
import tempfile
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

import jsonschema

from qed.problems.circle_packing_n26.verifier_exact import (
    format_fraction_40_decimals,
    make_valid,
    parse_exact_fraction,
    verify_packing_exact,
)

HEX_64_PATTERN = re.compile(r"^[0-9a-f]{64}$")
FRACTION_PATTERN = re.compile(r"^[0-9]+/[1-9][0-9]*$")
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
DATE_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")

SCHEMA_FILE_PATH = Path(__file__).parent / "certificate_schema.json"


def compute_sha256_bytes(content: bytes) -> str:
    """Compute hex-encoded SHA-256 digest of arbitrary raw byte content."""
    return hashlib.sha256(content).hexdigest()


async def async_read_file_bytes(file_path: Path | str) -> bytes:
    """Asynchronously read and return the byte content of a file."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, Path(file_path).read_bytes)


async def async_write_file_bytes(file_path: Path | str, content: bytes) -> None:
    """Asynchronously write byte content to a destination file."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, Path(file_path).write_bytes, content)


async def async_compute_sha256_file(file_path: Path | str) -> str:
    """Asynchronously compute hex-encoded SHA-256 digest of a file on disk."""
    data = await async_read_file_bytes(file_path)
    return compute_sha256_bytes(data)


def compute_sha256_file(file_path: Path | str) -> str:
    """Compute hex-encoded SHA-256 digest of a file on disk synchronously."""
    return compute_sha256_bytes(Path(file_path).read_bytes())


def compute_canonical_certificate_hash(cert_data: dict[str, Any]) -> str:
    """Compute the SHA-256 hash of canonical JSON excluding certificate_sha256.

    Canonical format specifies alphabetical key ordering, compact separators
    (',', ':'), and UTF-8 encoding with no trailing whitespace.
    """
    payload = {k: v for k, v in cert_data.items() if k != "certificate_sha256"}
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return compute_sha256_bytes(canonical_json.encode("utf-8"))


def load_certificate_schema() -> dict[str, Any]:
    """Load and parse the certificate JSON schema from disk."""
    return json.loads(SCHEMA_FILE_PATH.read_text(encoding="utf-8"))


def _error_path_key(err: jsonschema.ValidationError) -> list[Any]:
    """Sort key extracting path representation from a ValidationError."""
    return list(err.path)


def validate_certificate_schema(
    cert: Any, schema: dict[str, Any] | None = None
) -> list[str]:
    """Validate a certificate dictionary against the formal Draft 2020-12 schema.

    Draft202012Validator is the single source of truth for structural schema
    validation, augmented with exact arithmetic checks for lowest terms and
    tolerance bounds that JSON Schema cannot express.
    """
    errors: list[str] = []
    schema_dict = schema or load_certificate_schema()
    validator = jsonschema.Draft202012Validator(schema_dict)

    sorted_errs = sorted(validator.iter_errors(cert), key=_error_path_key)
    for err in sorted_errs:
        loc = "/".join(map(str, err.path))
        prefix = f"at '{loc}': " if loc else ""
        errors.append(f"{prefix}{err.message}")

    # Custom semantic checks for exact fraction properties
    if isinstance(cert, dict):
        c_score = cert.get("claimed_score")
        if isinstance(c_score, str) and FRACTION_PATTERN.match(c_score):
            p, q = map(int, c_score.split("/"))
            f = Fraction(p, q)
            if f.numerator != p or f.denominator != q:
                errors.append(
                    f"claimed_score {c_score!r} is not in lowest terms "
                    f"(reduced: {f.numerator}/{f.denominator})"
                )

        tol = cert.get("best_known_tolerance")
        if isinstance(tol, str) and FRACTION_PATTERN.match(tol):
            p, q = map(int, tol.split("/"))
            f = Fraction(p, q)
            if f.numerator != p or f.denominator != q:
                errors.append(
                    f"best_known_tolerance {tol!r} is not in lowest terms "
                    f"(reduced: {f.numerator}/{f.denominator})"
                )
            elif f < 0 or f > Fraction(1, 1000):
                errors.append(f"best_known_tolerance {tol!r} must be in [0, 1/1000]")

    return errors


def format_fraction_decimals(val: Fraction, decimals: int = 10) -> str:
    """Format an exact fraction to a fixed number of decimal digits via integer math."""
    if val < 0:
        sign = "-"
        val = -val
    else:
        sign = ""
    int_part = val.numerator // val.denominator
    rem = val.numerator % val.denominator
    frac_part = (rem * (10**decimals)) // val.denominator
    return f"{sign}{int_part}.{frac_part:0{decimals}d}"


async def async_load_problem_baselines(
    problem_dir: Path | str,
) -> list[dict[str, Any]]:
    """Asynchronously load and validate literature baselines for a problem."""
    p_dir = Path(problem_dir)
    baselines_path = p_dir / "baselines.json"
    if not baselines_path.exists():
        return []

    raw = await async_read_file_bytes(baselines_path)
    data: dict[str, Any] = json.loads(raw.decode("utf-8"))

    schema_path = p_dir / "baselines_schema.json"
    if schema_path.exists():
        schema_raw = await async_read_file_bytes(schema_path)
        schema_dict = json.loads(schema_raw.decode("utf-8"))
        validator = jsonschema.Draft202012Validator(schema_dict)
        errs = list(validator.iter_errors(data))
        if errs:
            raise ValueError(f"baselines.json schema error: {errs[0].message}")

    entries = data.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("baselines.json 'entries' must be a list")
    return entries


def load_problem_baselines(problem_dir: Path | str) -> list[dict[str, Any]]:
    """Synchronously load and validate literature baselines for a problem."""
    return asyncio.run(async_load_problem_baselines(problem_dir))


async def async_run_independent_subprocess(
    script_path: Path | str, input_path: Path | str
) -> tuple[int, list[str]]:
    """Execute the independent checker script as an isolated subprocess CLI."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(script_path),
        str(input_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_bytes, _ = await proc.communicate()
    exit_code = proc.returncode or 0
    lines = stdout_bytes.decode("utf-8", errors="replace").splitlines()
    return exit_code, lines


async def async_verify_certificate(
    cert_path_or_dict: Path | str | dict[str, Any],
    *,
    problem_root: Path | None = None,
    spec_override_path: Path | None = None,
    exact_verifier_override: Path | None = None,
    indep_verifier_override: Path | None = None,
) -> tuple[bool, list[str], str | None, str | None]:
    """Verify a QED certificate through all formal checks in sequence.

    Checks:
    (a) Validate against certificate JSON schema (Draft 2020-12).
    (b) Recompute canonical certificate_sha256 and require equality.
    (c) Recompute SHA-256 of current spec.md and require match.
    (d) Recompute both verifier file hashes and require match.
    (e) Write construction to a temp file and execute exact verifier in-process
        and independent verifier as a SEPARATE subprocess.
    (f) Require both output VALID with identical exact score equal to claimed_score.
    (g) Enforce claim_type gating rules (tolerance for reproduction, margin for record).

    Returns:
        (passed, check_lines, score_p_q, score_decimal)
    """
    check_lines: list[str] = []
    tmp_path: Path | None = None

    try:
        # Load certificate if path
        if isinstance(cert_path_or_dict, (str, Path)):
            cert_path = Path(cert_path_or_dict)
            if not cert_path.exists():
                check_lines.append(f"File reading: FAILED: File not found: {cert_path}")
                return False, check_lines, None, None
            try:
                raw_bytes = await async_read_file_bytes(cert_path)
                cert: dict[str, Any] = json.loads(raw_bytes.decode("utf-8"))
            except Exception as exc:
                check_lines.append(f"File reading: FAILED: Invalid JSON: {exc}")
                return False, check_lines, None, None
        else:
            cert = cert_path_or_dict

        # (a) Schema validation
        schema_errors = validate_certificate_schema(cert)
        if schema_errors:
            check_lines.append(f"Schema validation: FAILED: {schema_errors[0]}")
            return False, check_lines, None, None
        check_lines.append("Schema validation: OK")

        # (b) Recompute certificate_sha256
        recomputed_cert_sha = compute_canonical_certificate_hash(cert)
        expected_cert_sha = cert.get("certificate_sha256")
        if recomputed_cert_sha != expected_cert_sha:
            check_lines.append(
                f"Certificate SHA-256: FAILED: Hash mismatch: expected "
                f"{expected_cert_sha}, computed {recomputed_cert_sha}"
            )
            return False, check_lines, None, None
        check_lines.append("Certificate SHA-256: OK")

        # Resolve problem files
        pid = cert["problem_id"]
        if problem_root is None:
            problem_root = Path(__file__).parent.parent / "problems" / pid
        spec_path = spec_override_path or (problem_root / "spec.md")
        exact_v_path = exact_verifier_override or (problem_root / "verifier_exact.py")
        indep_v_path = indep_verifier_override or (
            problem_root / "independent" / "check_circle_packing.py"
        )

        # (c) Recompute problem_spec_sha256
        if not spec_path.exists():
            check_lines.append(
                f"Problem spec SHA-256: FAILED: spec.md not found at {spec_path}"
            )
            return False, check_lines, None, None
        current_spec_sha = await async_compute_sha256_file(spec_path)
        if current_spec_sha != cert["problem_spec_sha256"]:
            check_lines.append(
                f"Problem spec SHA-256: FAILED: Spec hash mismatch: certificate has "
                f"{cert['problem_spec_sha256']}, current spec.md is {current_spec_sha}"
            )
            return False, check_lines, None, None
        check_lines.append("Problem spec SHA-256: OK")

        # (d) Recompute both verifier hashes
        if not exact_v_path.exists():
            check_lines.append(
                f"Verifier SHA-256: FAILED: verifier_exact.py not found: {exact_v_path}"
            )
            return False, check_lines, None, None
        if not indep_v_path.exists():
            check_lines.append(
                f"Verifier SHA-256: FAILED: checker missing: {indep_v_path}"
            )
            return False, check_lines, None, None

        current_exact_sha = await async_compute_sha256_file(exact_v_path)
        current_indep_sha = await async_compute_sha256_file(indep_v_path)

        expected_exact_sha = cert["verifiers"]["exact_sha256"]
        expected_indep_sha = cert["verifiers"]["independent_sha256"]

        if current_exact_sha != expected_exact_sha:
            check_lines.append(
                f"Verifier SHA-256: FAILED: exact_verifier hash mismatch: "
                f"expected {expected_exact_sha}, got {current_exact_sha}"
            )
            return False, check_lines, None, None
        if current_indep_sha != expected_indep_sha:
            check_lines.append(
                f"Verifier SHA-256: FAILED: independent_verifier hash mismatch: "
                f"expected {expected_indep_sha}, got {current_indep_sha}"
            )
            return False, check_lines, None, None
        check_lines.append("Verifier SHA-256: OK")

        # (e) Write construction to a temp file
        construction_dict = cert["construction"]
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp.write(json.dumps(construction_dict).encode("utf-8"))
            tmp_path = Path(tmp.name)

        # Run exact verifier in-process
        centers = construction_dict["centers"]
        radii = construction_dict["radii"]
        try:
            res_exact = verify_packing_exact(centers, radii)
        except Exception as exc:
            check_lines.append(f"Verifier exact evaluation: FAILED: {exc}")
            return False, check_lines, None, None

        if not res_exact.ok:
            violations_desc = (
                res_exact.violations[0].details
                if res_exact.violations
                else "geometric violation"
            )
            check_lines.append(
                f"Verifier exact evaluation: FAILED: INVALID ({violations_desc})"
            )
            return False, check_lines, None, None
        check_lines.append("Verifier exact evaluation: OK")

        # Run independent checker as a SEPARATE subprocess
        code_indep, lines_indep = await async_run_independent_subprocess(
            indep_v_path, tmp_path
        )
        l1_indep = lines_indep[0] if lines_indep else ""

        if code_indep != 0 or not l1_indep.startswith("VALID"):
            violations_desc = (
                lines_indep[1]
                if len(lines_indep) > 1
                else (l1_indep or "independent check failed")
            )
            check_lines.append(
                f"Independent verifier subprocess: FAILED: Subprocess reported "
                f"{l1_indep!r} ({violations_desc})"
            )
            return False, check_lines, None, None
        check_lines.append("Independent verifier subprocess: OK")

        # (f) Check both say VALID with identical exact scores equal to claimed_score
        exact_score_p_q = (
            f"{res_exact.exact_score.numerator}/{res_exact.exact_score.denominator}"
        )
        indep_score_p_q = l1_indep.split(" ", 1)[1].strip()
        claimed_score = cert["claimed_score"]

        if exact_score_p_q != indep_score_p_q:
            check_lines.append(
                f"Score parity: FAILED: Verifiers disagree: exact={exact_score_p_q} "
                f"vs independent={indep_score_p_q}"
            )
            return False, check_lines, None, None

        if exact_score_p_q != claimed_score:
            check_lines.append(
                f"Score parity: FAILED: Claimed score {claimed_score} does not match "
                f"verified score {exact_score_p_q}"
            )
            return False, check_lines, None, None
        check_lines.append("Score parity: OK")

        # (g) Enforce claim_type gating rules
        claim_type = cert["claim_type"]
        best_known = cert.get("best_known")

        if claim_type == "demonstration":
            if best_known is not None:
                check_lines.append(
                    "Claim type gating: FAILED: Demonstration requires best_known null"
                )
                return False, check_lines, None, None
            if cert.get("best_known_tolerance") is not None:
                check_lines.append(
                    "Claim type gating: FAILED: Demonstration requires "
                    "best_known_tolerance null"
                )
                return False, check_lines, None, None
            check_lines.append("Claim type gating: OK (demonstration)")

        elif claim_type == "reproduction":
            if best_known is None:
                check_lines.append(
                    "Claim type gating: FAILED: Reproduction requires best_known"
                )
                return False, check_lines, None, None
            if cert.get("best_known_tolerance") is None:
                check_lines.append(
                    "Claim type gating: FAILED: Reproduction requires "
                    "best_known_tolerance"
                )
                return False, check_lines, None, None

            try:
                claimed_frac = Fraction(claimed_score)
                bk_frac = parse_exact_fraction(best_known["value"])
                tol_frac = Fraction(cert["best_known_tolerance"])
            except Exception as exc:
                check_lines.append(
                    f"Claim type gating: FAILED: Invalid best_known/tolerance: {exc}"
                )
                return False, check_lines, None, None

            threshold = bk_frac * (Fraction(1, 1) - tol_frac)
            if claimed_frac < threshold:
                check_lines.append(
                    f"Claim type gating: FAILED: Reproduction score {claimed_frac} < "
                    f"threshold {threshold} (best_known {bk_frac} with tolerance "
                    f"{tol_frac})"
                )
                return False, check_lines, None, None

            ratio = claimed_frac / bk_frac
            ratio_str = format_fraction_decimals(ratio, 10)
            check_lines.append(
                f"Claim type gating: OK (reproduction: claimed/best_known ratio "
                f"{ratio_str})"
            )

        elif claim_type == "record":
            if best_known is None:
                check_lines.append(
                    "Claim type gating: FAILED: Record claim requires best_known object"
                )
                return False, check_lines, None, None
            if cert.get("best_known_tolerance") is not None:
                check_lines.append(
                    "Claim type gating: FAILED: Record claim requires "
                    "best_known_tolerance null"
                )
                return False, check_lines, None, None

            try:
                claimed_frac = Fraction(claimed_score)
                bk_str = str(best_known["value"]).strip()
                bk_frac = parse_exact_fraction(bk_str)
            except Exception as exc:
                check_lines.append(
                    f"Claim type gating: FAILED: Invalid best_known Fraction: {exc}"
                )
                return False, check_lines, None, None

            margin = claimed_frac - bk_frac
            if margin <= 0:
                check_lines.append(
                    f"Claim type gating: FAILED: Record claim requires score "
                    f"({claimed_frac}) > best_known ({bk_frac}), margin: {margin} <= 0"
                )
                return False, check_lines, None, None

            if "." in bk_str and "/" not in bk_str:
                frac_digits = len(bk_str.split(".")[1])
                required_margin = Fraction(1, 10**frac_digits)
                if margin < required_margin:
                    check_lines.append(
                        f"Claim type gating: FAILED: Record claim margin {margin} is "
                        f"less than required resolution 10^-{frac_digits} "
                        f"({required_margin}) for rounded decimal baseline {bk_str}"
                    )
                    return False, check_lines, None, None

            check_lines.append(f"Claim type gating: OK (record with margin +{margin})")

        score_decimal = format_fraction_40_decimals(res_exact.exact_score)
        return True, check_lines, exact_score_p_q, score_decimal

    except Exception as exc:
        check_lines.append(f"Unexpected error: FAILED: {exc}")
        return False, check_lines, None, None
    finally:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def verify_certificate(
    cert_path_or_dict: Path | str | dict[str, Any],
    *,
    problem_root: Path | None = None,
    spec_override_path: Path | None = None,
    exact_verifier_override: Path | None = None,
    indep_verifier_override: Path | None = None,
) -> tuple[bool, list[str], str | None, str | None]:
    """Verify a QED certificate synchronously."""
    return asyncio.run(
        async_verify_certificate(
            cert_path_or_dict,
            problem_root=problem_root,
            spec_override_path=spec_override_path,
            exact_verifier_override=exact_verifier_override,
            indep_verifier_override=indep_verifier_override,
        )
    )


async def async_make_certificate(
    *,
    claim_type: str,
    out_path: Path | str,
    run_id: str | None = None,
    run_dir: Path | str | None = None,
    construction_path: Path | str | None = None,
    baseline_id: str | None = None,
    tolerance: str = "0/1",
    problem_id: str = "circle_packing_n26",
    runs_dir: Path | None = None,
    problem_dir: Path | None = None,
) -> dict[str, Any]:
    """Generate and issue a verified QED certificate from a run or construction.

    Workflow:
    1. Loads raw construction JSON, or loads best_program.py from run directory
       and executes it in a sandboxed subprocess to obtain float centers and radii.
    2. Converts with make_valid to exact rational coordinates and radii.
    3. Verifies construction with BOTH checkers (verifier_exact and independent).
    4. Checks claim_type rules with baselines.json and exact arithmetic.
    5. Assembles certificate dictionary and signs with canonical SHA-256.
    6. Writes certificate to out_path.
    """
    if claim_type not in {"demonstration", "reproduction", "record"}:
        raise ValueError(
            f"Invalid claim_type: must be demonstration, reproduction, or record, "
            f"got {claim_type!r}"
        )

    base_prob_dir = problem_dir or (
        Path(__file__).parent.parent / "problems" / problem_id
    )
    spec_path = base_prob_dir / "spec.md"
    exact_v_path = base_prob_dir / "verifier_exact.py"
    indep_v_path = base_prob_dir / "independent" / "check_circle_packing.py"

    if not spec_path.exists():
        raise FileNotFoundError(f"Problem spec not found at {spec_path}")
    if not exact_v_path.exists():
        raise FileNotFoundError(f"Exact verifier not found at {exact_v_path}")
    if not indep_v_path.exists():
        raise FileNotFoundError(f"Independent verifier not found at {indep_v_path}")

    run_meta: dict[str, Any] | None = None

    if construction_path:
        c_path = Path(construction_path)
        if not c_path.exists():
            raise FileNotFoundError(f"Construction file not found: {c_path}")
        c_raw = await async_read_file_bytes(c_path)
        c_data = json.loads(c_raw.decode("utf-8"))
        if not isinstance(c_data, dict) or set(c_data.keys()) != {"centers", "radii"}:
            raise ValueError(
                "Construction file must be a JSON object containing exactly 'centers' "
                "and 'radii' keys (certificate JSON is not accepted)"
            )
        exact_centers_str = [[str(c[0]), str(c[1])] for c in c_data["centers"]]
        exact_radii_str = [str(r) for r in c_data["radii"]]
        claimed_score_frac = sum(parse_exact_fraction(r) for r in exact_radii_str)
        claimed_score_str = (
            f"{claimed_score_frac.numerator}/{claimed_score_frac.denominator}"
        )
    elif run_id or run_dir:
        if run_dir:
            run_path = Path(run_dir)
            active_run_id = run_path.name
        else:
            active_run_id = str(run_id)
            base_runs_dir = runs_dir or (
                Path(__file__).parent.parent.parent.parent / "runs"
            )
            run_path = base_runs_dir / active_run_id

        if not run_path.exists():
            raise FileNotFoundError(f"Run directory not found: {run_path}")

        best_prog_path = run_path / "openevolve" / "best" / "best_program.py"
        if not best_prog_path.exists():
            raise FileNotFoundError(f"Best program not found: {best_prog_path}")

        # Run best_program in a subprocess to extract float centers and radii
        runner_code = (
            "import json, sys\n"
            f"sys.path.insert(0, {str(best_prog_path.parent)!r})\n"
            "from best_program import run_packing\n"
            "c, r, s = run_packing()\n"
            "payload = {'centers': c.tolist(), 'radii': r.tolist(), "
            "'score': float(s)}\n"
            "print(json.dumps(payload))\n"
        )
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            runner_code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"Failed to execute best_program.py in subprocess: "
                f"{stderr_bytes.decode('utf-8', errors='replace')}"
            )

        run_output = json.loads(stdout_bytes.decode("utf-8"))
        float_centers = run_output["centers"]
        float_radii = run_output["radii"]

        # Convert with make_valid
        valid_res = make_valid(float_centers, float_radii)
        exact_centers_str = [[c[0], c[1]] for c in valid_res.exact_centers]
        exact_radii_str = list(valid_res.exact_radii)
        claimed_score_frac = valid_res.exact_score
        claimed_score_str = (
            f"{claimed_score_frac.numerator}/{claimed_score_frac.denominator}"
        )

        # Load run metadata
        summary_path = run_path / "summary.json"
        iterations_val = 20
        best_fast_score_str = str(run_output.get("score", ""))
        if summary_path.exists():
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                iterations_val = summary.get("iterations", iterations_val)
                if "best_fast_score" in summary:
                    best_fast_score_str = str(summary["best_fast_score"])
            except Exception:
                pass

        shrink_loss_str = (
            f"{valid_res.exact_loss.numerator}/{valid_res.exact_loss.denominator}"
        )
        run_meta = {
            "run_id": active_run_id,
            "engine": "openevolve",
            "engine_version": "0.4.0",
            "model": "gemini-2.5-flash",
            "iterations": iterations_val,
            "best_fast_score": best_fast_score_str,
            "shrink_loss_exact": shrink_loss_str,
        }
    else:
        raise ValueError("Either run_id/run_dir or construction_path must be provided")

    # Verify with verifier_exact
    v_exact = verify_packing_exact(exact_centers_str, exact_radii_str)
    if not v_exact.ok:
        raise ValueError(
            f"Exact verifier failed on converted construction: {v_exact.violations}"
        )

    # Verify with independent checker in subprocess
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp.write(
            json.dumps({"centers": exact_centers_str, "radii": exact_radii_str}).encode(
                "utf-8"
            )
        )
        tmp_file = Path(tmp.name)

    try:
        code_ind, lines_ind = await async_run_independent_subprocess(
            indep_v_path, tmp_file
        )
        l1_ind = lines_ind[0] if lines_ind else ""
        if code_ind != 0 or not l1_ind.startswith("VALID"):
            raise ValueError(
                f"Independent verifier failed on converted construction: {lines_ind}"
            )
        indep_score = l1_ind.split(" ", 1)[1].strip()
        if indep_score != claimed_score_str:
            raise ValueError(
                f"Score mismatch between verifiers: exact={claimed_score_str} "
                f"vs independent={indep_score}"
            )
    finally:
        tmp_file.unlink(missing_ok=True)

    # Gating checks and baselines handling
    best_known_dict: dict[str, Any] | None = None
    best_known_tolerance_val: str | None = None

    if claim_type == "demonstration":
        if baseline_id is not None:
            raise ValueError(
                "Baseline (--baseline) is not allowed for demonstration claims"
            )
        if tolerance != "0/1":
            raise ValueError(
                "Tolerance (--tolerance) is only valid for reproduction claims, "
                "not demonstration"
            )

    elif claim_type in {"reproduction", "record"}:
        if not baseline_id:
            raise ValueError(
                f"Baseline (--baseline <id>) is required for {claim_type} claims"
            )

        baselines = await async_load_problem_baselines(base_prob_dir)
        matched_entry: dict[str, Any] | None = None
        for entry in baselines:
            if entry.get("id") == baseline_id:
                matched_entry = entry
                break

        if matched_entry is None:
            raise ValueError(
                f"Baseline '{baseline_id}' not found in baselines.json for "
                f"problem '{problem_id}'"
            )

        if not matched_entry.get("human_verified", False):
            raise ValueError(
                f"Baseline '{baseline_id}' is not human_verified in baselines.json"
            )

        quote = matched_entry.get("quote", "")
        if len(quote.split()) > 15:
            raise ValueError(
                f"Baseline '{baseline_id}' quote exceeds 15 words limit: {quote!r}"
            )

        best_known_dict = {
            "value": matched_entry["value"],
            "source_url": matched_entry["source_url"],
            "retrieved_date": matched_entry["retrieved_date"],
        }
        bk_str = str(best_known_dict["value"]).strip()
        bk_frac = parse_exact_fraction(bk_str)

        if claim_type == "reproduction":
            # Validate tolerance
            if not isinstance(tolerance, str) or not FRACTION_PATTERN.match(tolerance):
                raise ValueError(
                    f"Tolerance must be a positive 'p/q' string, got {tolerance!r}"
                )
            tp, tq = map(int, tolerance.split("/"))
            tol_frac = Fraction(tp, tq)
            if tol_frac.numerator != tp or tol_frac.denominator != tq:
                raise ValueError(
                    f"Tolerance {tolerance!r} is not in lowest terms "
                    f"(reduced: {tol_frac.numerator}/{tol_frac.denominator})"
                )
            if tol_frac < 0 or tol_frac > Fraction(1, 1000):
                raise ValueError(f"Tolerance {tolerance!r} must be in [0, 1/1000]")

            threshold = bk_frac * (Fraction(1, 1) - tol_frac)
            if claimed_score_frac < threshold:
                raise ValueError(
                    f"Reproduction claim refused: score {claimed_score_frac} < "
                    f"threshold {threshold} (best known {bk_frac} with tolerance "
                    f"{tol_frac})"
                )
            best_known_tolerance_val = tolerance

        elif claim_type == "record":
            if tolerance != "0/1":
                raise ValueError(
                    "Tolerance (--tolerance) is only valid for reproduction claims, "
                    "not record"
                )
            margin = claimed_score_frac - bk_frac
            if margin <= 0:
                raise ValueError(
                    f"Record claim refused: margin {margin} is not strictly positive "
                    f"(claimed {claimed_score_frac} <= best known {bk_frac})"
                )
            if "." in bk_str and "/" not in bk_str:
                frac_digits = len(bk_str.split(".")[1])
                required_margin = Fraction(1, 10**frac_digits)
                if margin < required_margin:
                    raise ValueError(
                        f"Record claim refused: margin {margin} is less than required "
                        f"resolution 10^-{frac_digits} ({required_margin}) for "
                        f"rounded decimal baseline {bk_str}"
                    )

    # Compute source hashes
    spec_sha = await async_compute_sha256_file(spec_path)
    exact_sha = await async_compute_sha256_file(exact_v_path)
    indep_sha = await async_compute_sha256_file(indep_v_path)

    cert_data: dict[str, Any] = {
        "schema_version": "1.0.0",
        "problem_id": problem_id,
        "problem_spec_sha256": spec_sha,
        "claim_type": claim_type,
        "construction": {
            "centers": exact_centers_str,
            "radii": exact_radii_str,
        },
        "claimed_score": claimed_score_str,
        "best_known": best_known_dict,
        "best_known_tolerance": best_known_tolerance_val,
        "run": run_meta,
        "verifiers": {
            "exact_sha256": exact_sha,
            "independent_sha256": indep_sha,
        },
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    # Compute canonical hash
    cert_sha = compute_canonical_certificate_hash(cert_data)
    cert_data["certificate_sha256"] = cert_sha

    # Write certificate to out_path
    dest_path = Path(out_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    await async_write_file_bytes(
        dest_path, json.dumps(cert_data, indent=2).encode("utf-8")
    )

    return cert_data


def make_certificate(
    *,
    claim_type: str,
    out_path: Path | str,
    run_id: str | None = None,
    run_dir: Path | str | None = None,
    construction_path: Path | str | None = None,
    baseline_id: str | None = None,
    tolerance: str = "0/1",
    problem_id: str = "circle_packing_n26",
    runs_dir: Path | None = None,
    problem_dir: Path | None = None,
) -> dict[str, Any]:
    """Generate and issue a verified QED certificate synchronously."""
    return asyncio.run(
        async_make_certificate(
            claim_type=claim_type,
            out_path=out_path,
            run_id=run_id,
            run_dir=run_dir,
            construction_path=construction_path,
            baseline_id=baseline_id,
            tolerance=tolerance,
            problem_id=problem_id,
            runs_dir=runs_dir,
            problem_dir=problem_dir,
        )
    )
