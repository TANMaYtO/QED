"""Tests for certificate generation, schema validation, and verification.

Includes tamper tests covering distinct failure scenarios, CLI integration tests,
claim-type semantics, baseline registry gating, and full coverage of
src/qed/trust/certificate.py.
"""

from __future__ import annotations

import copy
import json
from fractions import Fraction
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from qed.cli import handle_make_cert_command, handle_verify_command
from qed.problems.circle_packing_n26.verifier_exact import (
    VerificationResult,
    format_fraction_40_decimals,
)
from qed.trust.certificate import (
    compute_canonical_certificate_hash,
    compute_sha256_file,
    format_fraction_decimals,
    load_certificate_schema,
    load_problem_baselines,
    make_certificate,
    validate_certificate_schema,
    verify_certificate,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "certificates"
DEMO_FIXTURE_PATH = FIXTURES_DIR / "demonstration_5x5_plus_1.json"
DEMO_SMOKE_FIXTURE_PATH = FIXTURES_DIR / "demonstration_smoke_run.json"
REPRO_FIXTURE_PATH = FIXTURES_DIR / "reproduction_fixture_synthetic.json"
TAMPERED_FIXTURE_PATH = FIXTURES_DIR / "tampered_score.json"


def load_demo_cert() -> dict[str, Any]:
    """Load a fresh copy of the demonstration certificate fixture."""
    return json.loads(DEMO_FIXTURE_PATH.read_text(encoding="utf-8"))


def load_smoke_cert() -> dict[str, Any]:
    """Load a fresh copy of the smoke run demonstration certificate fixture."""
    return json.loads(DEMO_SMOKE_FIXTURE_PATH.read_text(encoding="utf-8"))


def load_repro_cert() -> dict[str, Any]:
    """Load a fresh copy of the synthetic reproduction certificate fixture."""
    return json.loads(REPRO_FIXTURE_PATH.read_text(encoding="utf-8"))


def create_test_run(
    parent_dir: Path,
    run_id: str = "mock_run_001",
    score: str = "2.166666",
) -> Path:
    """Create a self-contained mock run directory for testing make_certificate."""
    run_dir = parent_dir / run_id
    best_dir = run_dir / "openevolve" / "best"
    best_dir.mkdir(parents=True, exist_ok=True)

    prog_code = (
        "import numpy as np\n"
        "def run_packing():\n"
        "    grid = [i / 12 for i in (1, 3, 5, 7, 9)]\n"
        "    pts = [[x, y] for y in grid for x in grid] + [[11 / 12, 11 / 12]]\n"
        "    c = np.array(pts, dtype=float)\n"
        "    r = np.full(26, 1 / 12, dtype=float)\n"
        f"    return c, r, {score}\n"
    )
    (best_dir / "best_program.py").write_text(prog_code, encoding="utf-8")
    summary = {
        "run_id": run_id,
        "iterations": 20,
        "best_fast_score": float(score),
    }
    (run_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return run_dir


def setup_mock_problem_dir(parent_dir: Path) -> Path:
    """Set up a fully functional mock problem directory with baselines."""
    prob_dir = parent_dir / "circle_packing_n26"
    prob_dir.mkdir(parents=True, exist_ok=True)
    real_prob = (
        Path(__file__).parent.parent / "src" / "qed" / "problems" / "circle_packing_n26"
    )
    (prob_dir / "spec.md").write_bytes((real_prob / "spec.md").read_bytes())
    (prob_dir / "verifier_exact.py").write_bytes(
        (real_prob / "verifier_exact.py").read_bytes()
    )
    indep_dir = prob_dir / "independent"
    indep_dir.mkdir(parents=True, exist_ok=True)
    (indep_dir / "check_circle_packing.py").write_bytes(
        (real_prob / "independent" / "check_circle_packing.py").read_bytes()
    )
    (prob_dir / "baselines_schema.json").write_bytes(
        (real_prob / "baselines_schema.json").read_bytes()
    )

    baselines_content = {
        "$schema": "./baselines_schema.json",
        "entries": [
            {
                "id": "known_repro_baseline",
                "value": "216666666666666629/100000000000000000",
                "source_url": "https://example.invalid/baseline",
                "retrieved_date": "2026-10-18",
                "quote": "Known baseline proof",
                "human_verified": True,
                "verified_on": "2026-10-18",
            },
            {
                "id": "known_record_baseline",
                "value": "3/2",
                "source_url": "https://example.invalid/old_record",
                "retrieved_date": "2026-10-18",
                "quote": "Previous record claim",
                "human_verified": True,
                "verified_on": "2026-10-18",
            },
            {
                "id": "known_record_tight",
                "value": "2.5333333",
                "source_url": "https://example.invalid/tight",
                "retrieved_date": "2026-10-18",
                "quote": "Tight decimal baseline",
                "human_verified": True,
                "verified_on": "2026-10-18",
            },
            {
                "id": "unverified_baseline",
                "value": "2.0",
                "source_url": "https://example.invalid/unverified",
                "retrieved_date": "2026-10-18",
                "quote": "Unverified entry",
                "human_verified": False,
                "verified_on": None,
            },
            {
                "id": "long_quote_baseline",
                "value": "2.0",
                "source_url": "https://example.invalid/long",
                "retrieved_date": "2026-10-18",
                "quote": (
                    "one two three four five six seven eight nine ten "
                    "eleven twelve thirteen fourteen fifteen sixteen"
                ),
                "human_verified": True,
                "verified_on": "2026-10-18",
            },
        ],
    }
    (prob_dir / "baselines.json").write_text(
        json.dumps(baselines_content), encoding="utf-8"
    )
    return prob_dir


def test_fixtures_exist_and_validate_schema() -> None:
    """Validate that all 4 certificate fixtures exist and pass schema checks."""
    assert DEMO_FIXTURE_PATH.exists()
    assert DEMO_SMOKE_FIXTURE_PATH.exists()
    assert REPRO_FIXTURE_PATH.exists()
    assert TAMPERED_FIXTURE_PATH.exists()

    assert validate_certificate_schema(load_demo_cert()) == []
    assert validate_certificate_schema(load_smoke_cert()) == []
    assert validate_certificate_schema(load_repro_cert()) == []
    assert (
        validate_certificate_schema(json.loads(TAMPERED_FIXTURE_PATH.read_text())) == []
    )


def test_verify_good_demonstration() -> None:
    """Validate that the demonstration certificate passes all checks."""
    passed, check_lines, score_p_q, score_dec = verify_certificate(DEMO_FIXTURE_PATH)
    assert passed is True
    assert score_p_q == "38/15"
    assert score_dec == "2.5333333333333333333333333333333333333333"
    assert any("Schema validation: OK" in line for line in check_lines)
    assert any("Certificate SHA-256: OK" in line for line in check_lines)
    assert any("Problem spec SHA-256: OK" in line for line in check_lines)
    assert any("Verifier SHA-256: OK" in line for line in check_lines)
    assert any("Verifier exact evaluation: OK" in line for line in check_lines)
    assert any("Independent verifier subprocess: OK" in line for line in check_lines)
    assert any("Score parity: OK" in line for line in check_lines)
    assert any("Claim type gating: OK (demonstration)" in line for line in check_lines)


def test_verify_good_demonstration_smoke_run() -> None:
    """Validate that the demonstration smoke run certificate passes all checks."""
    passed, check_lines, score_p_q, score_dec = verify_certificate(
        DEMO_SMOKE_FIXTURE_PATH
    )
    assert passed is True
    assert score_p_q == "1787146240596586469/1000000000000000000"
    assert score_dec == "1.7871462405965864690000000000000000000000"
    assert any("Claim type gating: OK (demonstration)" in line for line in check_lines)


def test_verify_good_reproduction() -> None:
    """Validate that the reproduction certificate passes all checks."""
    passed, check_lines, score_p_q, score_dec = verify_certificate(REPRO_FIXTURE_PATH)
    assert passed is True
    assert score_p_q == "38/15"
    assert score_dec == "2.5333333333333333333333333333333333333333"
    assert any(
        "Claim type gating: OK (reproduction: claimed/best_known ratio 1.0000000000)"
        in line
        for line in check_lines
    )


def test_reproduction_1787_against_2635_fails() -> None:
    """Test reproduction claim of 1.787... against 2.635 baseline fails."""
    cert = load_smoke_cert()
    cert["claim_type"] = "reproduction"
    cert["best_known"] = {
        "value": "2.635",
        "source_url": "https://example.invalid/baseline",
        "retrieved_date": "2026-10-18",
    }
    cert["best_known_tolerance"] = "1/1000"
    cert["certificate_sha256"] = compute_canonical_certificate_hash(cert)

    passed, check_lines, _, _ = verify_certificate(cert)
    assert passed is False
    assert any(
        "Reproduction score" in line and "< threshold" in line for line in check_lines
    )


def test_record_beating_6_decimal_baseline_resolution() -> None:
    """Test record claim resolution against 6-decimal rounded baseline."""
    cert = load_demo_cert()
    cert["claim_type"] = "record"
    cert["best_known_tolerance"] = None
    cert["best_known"] = {
        "value": "2.533333",
        "source_url": "https://example.invalid/decimal",
        "retrieved_date": "2026-10-18",
    }
    base_val = Fraction(2533333, 1000000)

    # Subcase A: Margin +10^-9 < 10^-6 -> fails
    score_small = base_val + Fraction(1, 10**9)
    cert["claimed_score"] = f"{score_small.numerator}/{score_small.denominator}"
    cert["certificate_sha256"] = compute_canonical_certificate_hash(cert)

    mock_res = VerificationResult(
        ok=True,
        exact_score=score_small,
        score_decimal=format_fraction_40_decimals(score_small),
        violations=[],
    )
    with (
        patch("qed.trust.certificate.verify_packing_exact", return_value=mock_res),
        patch(
            "qed.trust.certificate.async_run_independent_subprocess",
            return_value=(0, [f"VALID {cert['claimed_score']}"]),
        ),
    ):
        passed, check_lines, _, _ = verify_certificate(cert)
        assert passed is False
        assert any(
            "Record claim margin 1/1000000000 is less than required resolution 10^-6"
            in line
            for line in check_lines
        )

    # Subcase B: Margin +10^-6 >= 10^-6 -> passes
    score_valid = base_val + Fraction(1, 10**6)
    cert["claimed_score"] = f"{score_valid.numerator}/{score_valid.denominator}"
    cert["certificate_sha256"] = compute_canonical_certificate_hash(cert)
    mock_res_valid = VerificationResult(
        ok=True,
        exact_score=score_valid,
        score_decimal=format_fraction_40_decimals(score_valid),
        violations=[],
    )
    with (
        patch(
            "qed.trust.certificate.verify_packing_exact", return_value=mock_res_valid
        ),
        patch(
            "qed.trust.certificate.async_run_independent_subprocess",
            return_value=(0, [f"VALID {cert['claimed_score']}"]),
        ),
    ):
        passed, check_lines, _, _ = verify_certificate(cert)
        assert passed is True
        assert any(
            "Claim type gating: OK (record with margin +1/1000000)" in line
            for line in check_lines
        )


def test_tamper_1_coordinate_changed() -> None:
    """Tamper 1: Changing one coordinate causes verification to fail on geometry."""
    cert = load_demo_cert()
    cert["construction"]["centers"][0] = ["1/50", "1/10"]
    cert["certificate_sha256"] = compute_canonical_certificate_hash(cert)

    passed, check_lines, _, _ = verify_certificate(cert)
    assert passed is False
    assert any(
        "Verifier exact evaluation: FAILED: INVALID" in line for line in check_lines
    )


def test_tamper_2_claimed_score_changed() -> None:
    """Tamper 2: Changing claimed score causes score parity failure."""
    cert = load_demo_cert()
    cert["claimed_score"] = "37/15"
    cert["certificate_sha256"] = compute_canonical_certificate_hash(cert)

    passed, check_lines, _, _ = verify_certificate(cert)
    assert passed is False
    assert any(
        "Score parity: FAILED: Claimed score 37/15 does not match verified score 38/15"
        in line
        for line in check_lines
    )


def test_tamper_3_claim_type_record_without_margin() -> None:
    """Tamper 3: Changing claim_type to record fails when margin is non-positive."""
    cert = load_demo_cert()
    cert["claim_type"] = "record"
    cert["best_known"] = {
        "value": "38/15",
        "source_url": "https://example.com/baseline",
        "retrieved_date": "2026-10-18",
    }
    cert["best_known_tolerance"] = None
    cert["certificate_sha256"] = compute_canonical_certificate_hash(cert)

    passed, check_lines, _, _ = verify_certificate(cert)
    assert passed is False
    assert any(
        "Record claim requires score (38/15) > best_known (38/15)" in line
        for line in check_lines
    )


def test_tamper_4_problem_spec_sha256_changed() -> None:
    """Tamper 4: Changing problem_spec_sha256 causes spec hash mismatch."""
    cert = load_demo_cert()
    cert["problem_spec_sha256"] = "0" * 64
    cert["certificate_sha256"] = compute_canonical_certificate_hash(cert)

    passed, check_lines, _, _ = verify_certificate(cert)
    assert passed is False
    assert any(
        "Problem spec SHA-256: FAILED: Spec hash mismatch" in line
        for line in check_lines
    )


def test_tamper_5_certificate_sha256_changed() -> None:
    """Tamper 5: Modifying certificate_sha256 directly causes hash mismatch."""
    cert = load_demo_cert()
    cert["certificate_sha256"] = "f" * 64

    passed, check_lines, _, _ = verify_certificate(cert)
    assert passed is False
    assert any(
        "Certificate SHA-256: FAILED: Hash mismatch" in line for line in check_lines
    )


def test_tamper_6_spec_edited_after_issuing(tmp_path: Path) -> None:
    """Tamper 6: Editing spec.md after issuing causes problem spec SHA-256 mismatch."""
    cert = load_demo_cert()
    fake_spec = tmp_path / "spec.md"
    fake_spec.write_text("# Tampered Spec", encoding="utf-8")

    passed, check_lines, _, _ = verify_certificate(cert, spec_override_path=fake_spec)
    assert passed is False
    assert any(
        "Problem spec SHA-256: FAILED: Spec hash mismatch" in line
        for line in check_lines
    )


def test_tamper_7_verifier_file_edited(tmp_path: Path) -> None:
    """Tamper 7: Editing verifier file causes verifier SHA-256 mismatch."""
    cert = load_demo_cert()
    fake_exact_v = tmp_path / "verifier_exact.py"
    fake_exact_v.write_text("# Tampered Verifier", encoding="utf-8")

    passed, check_lines, _, _ = verify_certificate(
        cert, exact_verifier_override=fake_exact_v
    )
    assert passed is False
    assert any(
        "Verifier SHA-256: FAILED: exact_verifier hash mismatch" in line
        for line in check_lines
    )


def test_tamper_8_missing_required_field() -> None:
    """Tamper 8: Removing a required field causes schema validation failure."""
    cert = load_demo_cert()
    del cert["claimed_score"]

    passed, check_lines, _, _ = verify_certificate(cert)
    assert passed is False
    assert any(
        "Schema validation: FAILED" in line
        and "'claimed_score' is a required property" in line
        for line in check_lines
    )


def test_tamper_9_unknown_field_added() -> None:
    """Tamper 9: Adding an unknown field causes schema validation failure."""
    cert = load_demo_cert()
    cert["extra_unauthorized_property"] = 12345

    passed, check_lines, _, _ = verify_certificate(cert)
    assert passed is False
    assert any(
        "Schema validation: FAILED" in line
        and "Additional properties are not allowed" in line
        for line in check_lines
    )


def test_tamper_10_invalid_construction_with_recomputed_hash() -> None:
    """Tamper 10: Swapping in an invalid construction fails on geometric validity."""
    cert = load_demo_cert()
    cert["construction"]["radii"][0] = "0/1"
    cert["claimed_score"] = "73/30"
    cert["certificate_sha256"] = compute_canonical_certificate_hash(cert)

    passed, check_lines, _, _ = verify_certificate(cert)
    assert passed is False
    assert any(
        "Verifier exact evaluation: FAILED: INVALID" in line for line in check_lines
    )


def test_tamper_11_independent_checker_reports_different_score(
    tmp_path: Path,
) -> None:
    """Tamper 11: Stub checker with wrong score causes parity failure."""
    cert = load_demo_cert()
    stub_script = tmp_path / "stub_checker.py"
    stub_script.write_text("print('VALID 99/1')", encoding="utf-8")

    cert["verifiers"]["independent_sha256"] = compute_sha256_file(stub_script)
    cert["certificate_sha256"] = compute_canonical_certificate_hash(cert)

    passed, check_lines, _, _ = verify_certificate(
        cert, indep_verifier_override=stub_script
    )
    assert passed is False
    assert any(
        "Score parity: FAILED: Verifiers disagree: exact=38/15 vs independent=99/1"
        in line
        for line in check_lines
    )


def test_make_cert_reproduction_and_demonstration(tmp_path: Path) -> None:
    """Test generating certificates via make_certificate end-to-end."""
    prob_dir = setup_mock_problem_dir(tmp_path)
    test_run = create_test_run(tmp_path)

    # Reproduction claim using baseline
    out_repro = tmp_path / "issued_repro.json"
    cert_repro = make_certificate(
        run_id=test_run.name,
        runs_dir=tmp_path,
        problem_dir=prob_dir,
        claim_type="reproduction",
        baseline_id="known_repro_baseline",
        tolerance="1/1000",
        out_path=out_repro,
    )
    assert out_repro.exists()
    assert cert_repro["claim_type"] == "reproduction"
    assert cert_repro["best_known_tolerance"] == "1/1000"
    assert verify_certificate(out_repro, problem_root=prob_dir)[0] is True

    # Demonstration claim
    out_demo = tmp_path / "issued_demo.json"
    cert_demo = make_certificate(
        run_id=test_run.name,
        runs_dir=tmp_path,
        problem_dir=prob_dir,
        claim_type="demonstration",
        out_path=out_demo,
    )
    assert out_demo.exists()
    assert cert_demo["best_known"] is None
    assert cert_demo["best_known_tolerance"] is None
    assert verify_certificate(out_demo, problem_root=prob_dir)[0] is True


def test_make_cert_record_positive_margin(tmp_path: Path) -> None:
    """Test issuing a record claim with a positive margin exceeding best_known."""
    prob_dir = setup_mock_problem_dir(tmp_path)
    test_run = create_test_run(tmp_path)
    out_record = tmp_path / "issued_record.json"

    cert_record = make_certificate(
        run_id=test_run.name,
        runs_dir=tmp_path,
        problem_dir=prob_dir,
        claim_type="record",
        baseline_id="known_record_baseline",
        out_path=out_record,
    )
    assert out_record.exists()
    assert cert_record["claim_type"] == "record"
    assert cert_record["best_known_tolerance"] is None
    assert verify_certificate(out_record, problem_root=prob_dir)[0] is True


def test_make_cert_refuses_non_positive_margin(tmp_path: Path) -> None:
    """Test that make_certificate refuses record certificate if margin <= 0."""
    prob_dir = setup_mock_problem_dir(tmp_path)
    base_file = prob_dir / "baselines.json"
    data = json.loads(base_file.read_text(encoding="utf-8"))
    data["entries"].append(
        {
            "id": "impossible_record",
            "value": "3/1",
            "source_url": "https://example.invalid/high",
            "retrieved_date": "2026-10-18",
            "quote": "High baseline",
            "human_verified": True,
            "verified_on": "2026-10-18",
        }
    )
    base_file.write_text(json.dumps(data), encoding="utf-8")

    test_run = create_test_run(tmp_path)
    out_path = tmp_path / "unwritten_record.json"
    with pytest.raises(ValueError, match="Record claim refused: margin"):
        make_certificate(
            run_id=test_run.name,
            runs_dir=tmp_path,
            problem_dir=prob_dir,
            claim_type="record",
            baseline_id="impossible_record",
            out_path=out_path,
        )
    assert not out_path.exists()


def test_make_cert_refuses_reproduction_below_threshold(tmp_path: Path) -> None:
    """Test that make_certificate refuses reproduction if score is below threshold."""
    prob_dir = setup_mock_problem_dir(tmp_path)
    base_file = prob_dir / "baselines.json"
    data = json.loads(base_file.read_text(encoding="utf-8"))
    data["entries"].append(
        {
            "id": "high_repro_baseline",
            "value": "2.500",
            "source_url": "https://example.invalid/high-repro",
            "retrieved_date": "2026-10-18",
            "quote": "Higher reproduction baseline",
            "human_verified": True,
            "verified_on": "2026-10-18",
        }
    )
    base_file.write_text(json.dumps(data), encoding="utf-8")

    test_run = create_test_run(tmp_path)  # score ~2.166
    out_path = tmp_path / "unwritten_repro.json"
    with pytest.raises(ValueError, match="Reproduction claim refused: score"):
        make_certificate(
            run_id=test_run.name,
            runs_dir=tmp_path,
            problem_dir=prob_dir,
            claim_type="reproduction",
            baseline_id="high_repro_baseline",
            tolerance="0/1",
            out_path=out_path,
        )
    assert not out_path.exists()


def test_make_cert_baseline_rejections(tmp_path: Path) -> None:
    """Test make_certificate rejection of unknown, unverified, or bad baselines."""
    prob_dir = setup_mock_problem_dir(tmp_path)
    test_run = create_test_run(tmp_path)
    out_path = tmp_path / "unwritten.json"

    # 1. Invalid claim_type
    with pytest.raises(ValueError, match="Invalid claim_type"):
        make_certificate(
            run_id=test_run.name,
            runs_dir=tmp_path,
            problem_dir=prob_dir,
            claim_type="invalid_type",
            out_path=out_path,
        )

    # 2. Unknown baseline
    with pytest.raises(ValueError, match="not found in baselines.json"):
        make_certificate(
            run_id=test_run.name,
            runs_dir=tmp_path,
            problem_dir=prob_dir,
            claim_type="reproduction",
            baseline_id="nonexistent_baseline_id",
            out_path=out_path,
        )

    # 3. Missing baseline_id for reproduction
    with pytest.raises(ValueError, match="is required for reproduction"):
        make_certificate(
            run_id=test_run.name,
            runs_dir=tmp_path,
            problem_dir=prob_dir,
            claim_type="reproduction",
            baseline_id=None,
            out_path=out_path,
        )

    # 4. Unverified baseline
    with pytest.raises(ValueError, match="is not human_verified in baselines.json"):
        make_certificate(
            run_id=test_run.name,
            runs_dir=tmp_path,
            problem_dir=prob_dir,
            claim_type="reproduction",
            baseline_id="unverified_baseline",
            out_path=out_path,
        )

    # 5. Quote exceeds 15 words
    with pytest.raises(ValueError, match="quote exceeds 15 words limit"):
        make_certificate(
            run_id=test_run.name,
            runs_dir=tmp_path,
            problem_dir=prob_dir,
            claim_type="reproduction",
            baseline_id="long_quote_baseline",
            out_path=out_path,
        )

    # 6. Demonstration with baseline provided
    with pytest.raises(ValueError, match="Baseline .* not allowed for demonstration"):
        make_certificate(
            run_id=test_run.name,
            runs_dir=tmp_path,
            problem_dir=prob_dir,
            claim_type="demonstration",
            baseline_id="known_repro_baseline",
            out_path=out_path,
        )

    # 7. Demonstration with tolerance provided
    with pytest.raises(ValueError, match="Tolerance .* only valid for reproduction"):
        make_certificate(
            run_id=test_run.name,
            runs_dir=tmp_path,
            problem_dir=prob_dir,
            claim_type="demonstration",
            tolerance="1/1000",
            out_path=out_path,
        )

    # 8. Record with tolerance provided
    with pytest.raises(ValueError, match="Tolerance .* only valid for reproduction"):
        make_certificate(
            run_id=test_run.name,
            runs_dir=tmp_path,
            problem_dir=prob_dir,
            claim_type="record",
            baseline_id="known_record_baseline",
            tolerance="1/1000",
            out_path=out_path,
        )

    # 9. Reproduction with tolerance > 1/1000
    with pytest.raises(ValueError, match="must be in \\[0, 1/1000\\]"):
        make_certificate(
            run_id=test_run.name,
            runs_dir=tmp_path,
            problem_dir=prob_dir,
            claim_type="reproduction",
            baseline_id="known_repro_baseline",
            tolerance="1/500",
            out_path=out_path,
        )

    # 10. Reproduction with non-reduced tolerance
    with pytest.raises(ValueError, match="is not in lowest terms"):
        make_certificate(
            run_id=test_run.name,
            runs_dir=tmp_path,
            problem_dir=prob_dir,
            claim_type="reproduction",
            baseline_id="known_repro_baseline",
            tolerance="0/2",
            out_path=out_path,
        )

    # 11. Reproduction with invalid tolerance string
    with pytest.raises(ValueError, match="Tolerance must be a positive 'p/q' string"):
        make_certificate(
            run_id=test_run.name,
            runs_dir=tmp_path,
            problem_dir=prob_dir,
            claim_type="reproduction",
            baseline_id="known_repro_baseline",
            tolerance="not_a_fraction",
            out_path=out_path,
        )


def test_cli_verify_and_make_cert(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test CLI commands 'qed verify' and 'qed make-cert' via argparse handlers."""

    class Args:
        pass

    # CLI verify good demo
    args = Args()
    args.certificate = str(DEMO_FIXTURE_PATH)
    ret = handle_verify_command(args)
    captured = capsys.readouterr().out
    assert ret == 0
    assert "PASS" in captured
    assert "Score (exact): 38/15" in captured

    # CLI verify bad path
    args.certificate = "nonexistent_cert_abc.json"
    ret = handle_verify_command(args)
    captured = capsys.readouterr().out
    assert ret == 1
    assert "FAIL" in captured

    # CLI make-cert
    test_run = create_test_run(tmp_path)
    out_cli = str(tmp_path / "cli_cert.json")
    args_mc = Args()
    args_mc.run_id = str(test_run)
    args_mc.claim_type = "demonstration"
    args_mc.baseline = None
    args_mc.tolerance = "0/1"
    args_mc.out = out_cli
    ret_mc = handle_make_cert_command(args_mc)
    captured_mc = capsys.readouterr().out
    assert ret_mc == 0
    assert "Certificate issued to" in captured_mc

    # CLI make-cert failure
    args_bad = Args()
    args_bad.run_id = "nonexistent_dir_999"
    args_bad.claim_type = "demonstration"
    args_bad.out = str(tmp_path / "never.json")
    ret_bad = handle_make_cert_command(args_bad)
    captured_bad = capsys.readouterr().out
    assert ret_bad == 1
    assert "make-cert FAILED" in captured_bad


def test_schema_validation_edge_cases() -> None:
    """Test detailed schema validation edge cases."""
    assert "is not of type 'object'" in validate_certificate_schema("not_a_dict")[0]

    cert = load_demo_cert()

    # Bad schema_version
    bad = copy.deepcopy(cert)
    bad["schema_version"] = "v1"
    assert any(
        "schema_version" in e and "does not match" in e
        for e in validate_certificate_schema(bad)
    )

    # Bad problem_id
    bad = copy.deepcopy(cert)
    bad["problem_id"] = ""
    assert any(
        "problem_id" in e and "does not match" in e
        for e in validate_certificate_schema(bad)
    )

    # Bad problem_spec_sha256
    bad = copy.deepcopy(cert)
    bad["problem_spec_sha256"] = "xyz"
    assert any(
        "problem_spec_sha256" in e and "does not match" in e
        for e in validate_certificate_schema(bad)
    )

    # Bad claim_type
    bad = copy.deepcopy(cert)
    bad["claim_type"] = "invalid"
    assert any("is not one of" in e for e in validate_certificate_schema(bad))

    # Bad claimed_score format
    bad = copy.deepcopy(cert)
    bad["claimed_score"] = "invalid"
    assert any("does not match" in e for e in validate_certificate_schema(bad))

    # Bad claimed_score not lowest terms
    bad = copy.deepcopy(cert)
    bad["claimed_score"] = "76/30"
    assert any("not in lowest terms" in e for e in validate_certificate_schema(bad))

    # Bad tolerance format
    bad = copy.deepcopy(load_repro_cert())
    bad["best_known_tolerance"] = "not_frac"
    assert any("does not match" in e for e in validate_certificate_schema(bad))

    # Bad tolerance not lowest terms
    bad["best_known_tolerance"] = "0/2"
    assert any("not in lowest terms" in e for e in validate_certificate_schema(bad))

    # Bad tolerance out of bounds
    bad["best_known_tolerance"] = "1/500"
    assert any("must be in [0, 1/1000]" in e for e in validate_certificate_schema(bad))

    # Demonstration with non-null best_known
    bad_demo = copy.deepcopy(cert)
    bad_demo["best_known"] = {
        "value": "1/2",
        "source_url": "https://example.com",
        "retrieved_date": "2026-10-18",
    }
    assert any("null" in e for e in validate_certificate_schema(bad_demo))

    # Demonstration with non-null best_known_tolerance
    bad_demo = copy.deepcopy(cert)
    bad_demo["best_known_tolerance"] = "0/1"
    assert any("null" in e for e in validate_certificate_schema(bad_demo))


def test_schema_load_function() -> None:
    """Test loading certificate schema directly from file."""
    schema = load_certificate_schema()
    assert isinstance(schema, dict)
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"


def test_verify_missing_verifier_files(tmp_path: Path) -> None:
    """Test verify_certificate failure when verifier files are missing."""
    cert = load_demo_cert()
    nonexistent = tmp_path / "nonexistent.py"

    passed, check_lines, _, _ = verify_certificate(
        cert, exact_verifier_override=nonexistent
    )
    assert passed is False
    assert any(
        "Verifier SHA-256: FAILED: verifier_exact.py not found" in line
        for line in check_lines
    )

    passed, check_lines, _, _ = verify_certificate(
        cert, indep_verifier_override=nonexistent
    )
    assert passed is False
    assert any(
        "Verifier SHA-256: FAILED: checker missing" in line for line in check_lines
    )


def test_tamper_wrong_independent_sha256() -> None:
    """Tamper: Wrong independent_sha256 causes verifier SHA-256 mismatch."""
    cert = load_demo_cert()
    cert["verifiers"]["independent_sha256"] = "0" * 64
    cert["certificate_sha256"] = compute_canonical_certificate_hash(cert)

    passed, check_lines, _, _ = verify_certificate(cert)
    assert passed is False
    assert any(
        "Verifier SHA-256: FAILED: independent_verifier hash mismatch" in line
        for line in check_lines
    )


def test_verify_malformed_json_file(tmp_path: Path) -> None:
    """Test verify_certificate on a file containing malformed JSON."""
    bad_json = tmp_path / "malformed.json"
    bad_json.write_text("{not valid json", encoding="utf-8")

    passed, check_lines, _, _ = verify_certificate(bad_json)
    assert passed is False
    assert any("File reading: FAILED: Invalid JSON" in line for line in check_lines)


def test_verify_missing_file() -> None:
    """Test verify_certificate on a non-existent file."""
    passed, check_lines, _, _ = verify_certificate("nonexistent_path_xyz.json")
    assert passed is False
    assert any("File reading: FAILED: File not found" in line for line in check_lines)


def test_verify_unknown_problem_id() -> None:
    """Test verify_certificate on a certificate referencing an unknown problem."""
    cert = load_demo_cert()
    cert["problem_id"] = "unknown_problem_xyz"
    cert["certificate_sha256"] = compute_canonical_certificate_hash(cert)

    passed, check_lines, _, _ = verify_certificate(cert)
    assert passed is False
    assert any(
        "Problem spec SHA-256: FAILED: spec.md not found" in line
        for line in check_lines
    )


def test_claim_type_gating_scenarios() -> None:
    """Test demonstration, reproduction, and record claim type gating rules."""
    # Demonstration with best_known not null (defensive check)
    cert_demo = load_demo_cert()
    cert_demo["best_known"] = {
        "value": "1/2",
        "source_url": "https://example.com",
        "retrieved_date": "2026-10-18",
    }
    cert_demo["certificate_sha256"] = compute_canonical_certificate_hash(cert_demo)
    with patch("qed.trust.certificate.validate_certificate_schema", return_value=[]):
        passed, lines, _, _ = verify_certificate(cert_demo)
        assert passed is False
        assert any("Demonstration requires best_known null" in line for line in lines)

    # Demonstration with best_known_tolerance not null (defensive check)
    cert_demo2 = load_demo_cert()
    cert_demo2["best_known_tolerance"] = "0/1"
    cert_demo2["certificate_sha256"] = compute_canonical_certificate_hash(cert_demo2)
    with patch("qed.trust.certificate.validate_certificate_schema", return_value=[]):
        passed, lines, _, _ = verify_certificate(cert_demo2)
        assert passed is False
        assert any(
            "Demonstration requires best_known_tolerance null" in line for line in lines
        )

    # Reproduction with best_known null (defensive check)
    cert_repro_null = load_repro_cert()
    cert_repro_null["best_known"] = None
    cert_repro_null["certificate_sha256"] = compute_canonical_certificate_hash(
        cert_repro_null
    )
    with patch("qed.trust.certificate.validate_certificate_schema", return_value=[]):
        passed, lines, _, _ = verify_certificate(cert_repro_null)
        assert passed is False
        assert any("Reproduction requires best_known" in line for line in lines)

    # Reproduction with tolerance null (defensive check)
    cert_repro_notol = load_repro_cert()
    cert_repro_notol["best_known_tolerance"] = None
    cert_repro_notol["certificate_sha256"] = compute_canonical_certificate_hash(
        cert_repro_notol
    )
    with patch("qed.trust.certificate.validate_certificate_schema", return_value=[]):
        passed, lines, _, _ = verify_certificate(cert_repro_notol)
        assert passed is False
        assert any(
            "Reproduction requires best_known_tolerance" in line for line in lines
        )

    # Reproduction with invalid best_known fraction
    cert_repro = load_repro_cert()
    cert_repro["best_known"]["value"] = "not_a_fraction"
    cert_repro["certificate_sha256"] = compute_canonical_certificate_hash(cert_repro)
    passed, lines, _, _ = verify_certificate(cert_repro)
    assert passed is False
    assert any("Invalid best_known/tolerance" in line for line in lines)

    # Record with best_known null (defensive check)
    cert_rec_null = load_demo_cert()
    cert_rec_null["claim_type"] = "record"
    cert_rec_null["best_known"] = None
    cert_rec_null["best_known_tolerance"] = None
    cert_rec_null["certificate_sha256"] = compute_canonical_certificate_hash(
        cert_rec_null
    )
    with patch("qed.trust.certificate.validate_certificate_schema", return_value=[]):
        passed, lines, _, _ = verify_certificate(cert_rec_null)
        assert passed is False
        assert any("Record claim requires best_known object" in line for line in lines)

    # Record with tolerance not null (defensive check)
    cert_rec_tol = load_demo_cert()
    cert_rec_tol["claim_type"] = "record"
    cert_rec_tol["best_known"] = {
        "value": "1/2",
        "source_url": "https://example.com",
        "retrieved_date": "2026-10-18",
    }
    cert_rec_tol["best_known_tolerance"] = "0/1"
    cert_rec_tol["certificate_sha256"] = compute_canonical_certificate_hash(
        cert_rec_tol
    )
    with patch("qed.trust.certificate.validate_certificate_schema", return_value=[]):
        passed, lines, _, _ = verify_certificate(cert_rec_tol)
        assert passed is False
        assert any(
            "Record claim requires best_known_tolerance null" in line for line in lines
        )

    # Record with invalid best_known fraction
    cert_rec = load_demo_cert()
    cert_rec["claim_type"] = "record"
    cert_rec["best_known"] = {
        "value": "not_a_fraction",
        "source_url": "https://example.com",
        "retrieved_date": "2026-10-18",
    }
    cert_rec["best_known_tolerance"] = None
    cert_rec["certificate_sha256"] = compute_canonical_certificate_hash(cert_rec)
    passed, lines, _, _ = verify_certificate(cert_rec)
    assert passed is False
    assert any("Invalid best_known Fraction" in line for line in lines)


def test_independent_verifier_subprocess_failure(tmp_path: Path) -> None:
    """Test independent verifier failing with non-zero exit code in subprocess."""
    cert = load_demo_cert()
    fail_script = tmp_path / "failing_checker.py"
    fail_script.write_text(
        "import sys\nprint('INVALID: geometric error')\nsys.exit(1)\n",
        encoding="utf-8",
    )

    cert["verifiers"]["independent_sha256"] = compute_sha256_file(fail_script)
    cert["certificate_sha256"] = compute_canonical_certificate_hash(cert)

    passed, lines, _, _ = verify_certificate(cert, indep_verifier_override=fail_script)
    assert passed is False
    assert any("Independent verifier subprocess: FAILED" in line for line in lines)


def test_make_cert_missing_components_and_summary_error(tmp_path: Path) -> None:
    """Test make_certificate failure on missing files and summary errors."""
    fake_run = tmp_path / "fake_run"
    fake_run.mkdir()
    out_file = tmp_path / "test_out.json"

    # Missing best_program.py
    with pytest.raises(FileNotFoundError, match="Best program not found"):
        make_certificate(
            run_id=fake_run.name,
            runs_dir=tmp_path,
            claim_type="demonstration",
            out_path=out_file,
        )

    # Missing spec.md in problem dir
    empty_prob = tmp_path / "empty_prob"
    empty_prob.mkdir()
    best_dir = fake_run / "openevolve" / "best"
    best_dir.mkdir(parents=True)
    (best_dir / "best_program.py").write_text("# dummy", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="Problem spec not found"):
        make_certificate(
            run_id=fake_run.name,
            runs_dir=tmp_path,
            problem_dir=empty_prob,
            claim_type="demonstration",
            out_path=out_file,
        )

    # Missing verifier_exact.py
    (empty_prob / "spec.md").write_text("# spec", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="Exact verifier not found"):
        make_certificate(
            run_id=fake_run.name,
            runs_dir=tmp_path,
            problem_dir=empty_prob,
            claim_type="demonstration",
            out_path=out_file,
        )

    # Missing independent verifier
    (empty_prob / "verifier_exact.py").write_text("# exact", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="Independent verifier not found"):
        make_certificate(
            run_id=fake_run.name,
            runs_dir=tmp_path,
            problem_dir=empty_prob,
            claim_type="demonstration",
            out_path=out_file,
        )


def test_make_cert_broken_best_program(tmp_path: Path) -> None:
    """Test make_certificate handling of broken best_program.py execution."""
    broken_run = tmp_path / "broken_run"
    best_dir = broken_run / "openevolve" / "best"
    best_dir.mkdir(parents=True)
    (best_dir / "best_program.py").write_text(
        "raise RuntimeError('broken')", encoding="utf-8"
    )

    with pytest.raises(RuntimeError, match="Failed to execute best_program.py"):
        make_certificate(
            run_id=broken_run.name,
            runs_dir=tmp_path,
            claim_type="demonstration",
            out_path=tmp_path / "never_written.json",
        )


def test_tamper_record_missing_best_known() -> None:
    """Tamper: record claim with best_known None fails claim type gating."""
    cert = load_demo_cert()
    cert["claim_type"] = "record"
    cert["best_known"] = None
    cert["certificate_sha256"] = compute_canonical_certificate_hash(cert)

    passed, lines, _, _ = verify_certificate(cert)
    assert passed is False
    assert any(
        "Record claim requires best_known object" in line
        or "Schema validation: FAILED" in line
        for line in lines
    )


def test_exact_verifier_exception_handling() -> None:
    """Test verify_certificate handling when exact verifier raises an exception."""
    cert = load_demo_cert()
    cert["construction"]["radii"][0] = "not_a_number"
    cert["certificate_sha256"] = compute_canonical_certificate_hash(cert)

    passed, lines, _, _ = verify_certificate(cert)
    assert passed is False
    assert any("Verifier exact evaluation: FAILED" in line for line in lines)


def test_make_cert_malformed_summary_json(tmp_path: Path) -> None:
    """Test make_certificate resilience when summary.json is unparseable."""
    test_run = create_test_run(tmp_path, run_id="run_bad_summary")
    out_cert = tmp_path / "cert_with_bad_summary.json"
    (test_run / "summary.json").write_text("{broken json", encoding="utf-8")

    cert = make_certificate(
        run_id=test_run.name,
        runs_dir=tmp_path,
        claim_type="demonstration",
        out_path=out_cert,
    )
    assert out_cert.exists()
    assert cert["run"]["iterations"] == 20
    assert verify_certificate(out_cert)[0] is True


def test_make_cert_from_construction_file(tmp_path: Path) -> None:
    """Test generating certificate directly from raw construction JSON."""
    c_file = tmp_path / "construction.json"
    demo_cert = load_demo_cert()
    c_file.write_text(json.dumps(demo_cert["construction"]), encoding="utf-8")

    out_file = tmp_path / "hand_built_cert.json"
    cert = make_certificate(
        construction_path=c_file,
        claim_type="demonstration",
        out_path=out_file,
    )
    assert out_file.exists()
    assert cert["run"] is None
    assert cert["claimed_score"] == "38/15"
    assert verify_certificate(out_file)[0] is True

    # Missing construction file
    with pytest.raises(FileNotFoundError, match="Construction file not found"):
        make_certificate(
            construction_path=tmp_path / "nonexistent_c.json",
            claim_type="demonstration",
            out_path=out_file,
        )

    # Missing both run_id and construction_path
    with pytest.raises(ValueError, match="Either run_id/run_dir or construction_path"):
        make_certificate(
            claim_type="demonstration",
            out_path=out_file,
        )


def test_make_cert_refuses_certificate_file_as_construction(tmp_path: Path) -> None:
    """Test make-cert explicitly refuses a certificate JSON passed as construction."""
    out_file = tmp_path / "cert_never.json"
    with pytest.raises(
        ValueError,
        match="Construction file must be a JSON object containing exactly",
    ):
        make_certificate(
            construction_path=DEMO_FIXTURE_PATH,
            claim_type="demonstration",
            out_path=out_file,
        )


def test_baselines_loading_edge_cases(tmp_path: Path) -> None:
    """Test load_problem_baselines edge cases."""
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    assert load_problem_baselines(empty_dir) == []

    bad_schema_dir = tmp_path / "bad_schema_dir"
    bad_schema_dir.mkdir()
    (bad_schema_dir / "baselines_schema.json").write_text(
        json.dumps({"type": "object", "required": ["entries"]}), encoding="utf-8"
    )
    (bad_schema_dir / "baselines.json").write_text(
        json.dumps({"wrong": 1}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="baselines.json schema error"):
        load_problem_baselines(bad_schema_dir)

    (bad_schema_dir / "baselines.json").write_text(
        json.dumps({"entries": "not_a_list"}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="entries' must be a list"):
        load_problem_baselines(bad_schema_dir)


def test_make_cert_coverage_branches(tmp_path: Path) -> None:
    """Test remaining branching paths in make_certificate for >= 99% coverage."""
    prob_dir = setup_mock_problem_dir(tmp_path)

    # 1. run_dir passed directly as Path
    test_run = create_test_run(tmp_path, run_id="run_dir_path_test")
    out_run_dir = tmp_path / "cert_run_dir.json"
    cert = make_certificate(
        run_dir=test_run,
        problem_dir=prob_dir,
        claim_type="demonstration",
        out_path=out_run_dir,
    )
    assert cert["run"]["run_id"] == "run_dir_path_test"

    # 2. Geometric violation in construction file passed to make_certificate
    bad_c = tmp_path / "bad_overlap.json"
    bad_payload = {
        "centers": [["1/2", "1/2"]] * 26,
        "radii": ["1/2"] * 26,
    }
    bad_c.write_text(json.dumps(bad_payload), encoding="utf-8")
    with pytest.raises(
        ValueError, match="Exact verifier failed on converted construction"
    ):
        make_certificate(
            construction_path=bad_c,
            problem_dir=prob_dir,
            claim_type="demonstration",
            out_path=tmp_path / "never.json",
        )

    # 3. Independent verifier reports failure during make_certificate
    failing_indep_dir = tmp_path / "prob_fail_indep"
    failing_indep_dir.mkdir(parents=True)
    setup_mock_problem_dir(tmp_path)
    (failing_indep_dir / "spec.md").write_bytes((prob_dir / "spec.md").read_bytes())
    (failing_indep_dir / "verifier_exact.py").write_bytes(
        (prob_dir / "verifier_exact.py").read_bytes()
    )
    indep_sub = failing_indep_dir / "independent"
    indep_sub.mkdir()
    (indep_sub / "check_circle_packing.py").write_text(
        "import sys\nprint('INVALID: geometric error')\nsys.exit(1)\n",
        encoding="utf-8",
    )
    good_c = tmp_path / "good_c.json"
    good_c.write_text(json.dumps(load_demo_cert()["construction"]), encoding="utf-8")
    with pytest.raises(
        ValueError, match="Independent verifier failed on converted construction"
    ):
        make_certificate(
            construction_path=good_c,
            problem_dir=failing_indep_dir,
            claim_type="demonstration",
            out_path=tmp_path / "never.json",
        )

    # 4. Independent verifier returns mismatched score during make_certificate
    (indep_sub / "check_circle_packing.py").write_text(
        "print('VALID 999/1')\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Score mismatch between verifiers"):
        make_certificate(
            construction_path=good_c,
            problem_dir=failing_indep_dir,
            claim_type="demonstration",
            out_path=tmp_path / "never.json",
        )

    # 5. Record claim with decimal baseline where margin < 10^-d during make_cert
    with pytest.raises(ValueError, match="less than required resolution"):
        make_certificate(
            construction_path=good_c,  # score 38/15 ~ 2.5333333333
            problem_dir=prob_dir,
            claim_type="record",
            # Baseline 2.5333333 (d=7) -> margin 1/30000000 < 10^-7
            baseline_id="known_record_tight",
            out_path=tmp_path / "never.json",
        )


def test_verify_unexpected_exception_handling() -> None:
    """Test verify_certificate handling of unexpected runtime exceptions."""

    class CrashingDict(dict[str, Any]):
        def __getitem__(self, key: str) -> Any:
            if key == "problem_id":
                raise RuntimeError("simulated crash")
            return super().__getitem__(key)

    cert = CrashingDict(load_demo_cert())
    passed, check_lines, _, _ = verify_certificate(cert)
    assert passed is False
    assert any(
        "Unexpected error: FAILED: simulated crash" in line for line in check_lines
    )


def test_format_fraction_decimals_negative() -> None:
    """Test format_fraction_decimals on a negative fraction."""
    neg_frac = Fraction(-7, 3)
    formatted = format_fraction_decimals(neg_frac, decimals=5)
    assert formatted == "-2.33333"
