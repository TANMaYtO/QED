"""Tests for certificate generation, schema validation, and verification.

Includes tamper tests covering 11 distinct failure scenarios, CLI integration tests,
and edge-case validation to ensure >= 95% coverage on src/qed/trust/certificate.py.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from qed.cli import handle_make_cert_command, handle_verify_command
from qed.trust.certificate import (
    compute_canonical_certificate_hash,
    compute_sha256_file,
    load_certificate_schema,
    make_certificate,
    validate_certificate_schema,
    verify_certificate,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "certificates"
DEMO_FIXTURE_PATH = FIXTURES_DIR / "demonstration_5x5_plus_1.json"
REPRO_FIXTURE_PATH = FIXTURES_DIR / "reproduction_smoke_run.json"


def load_demo_cert() -> dict[str, Any]:
    """Load a fresh copy of the demonstration certificate fixture."""
    return json.loads(DEMO_FIXTURE_PATH.read_text(encoding="utf-8"))


def load_repro_cert() -> dict[str, Any]:
    """Load a fresh copy of the reproduction certificate fixture."""
    return json.loads(REPRO_FIXTURE_PATH.read_text(encoding="utf-8"))


def test_fixtures_exist_and_validate_schema() -> None:
    """Validate that both good fixtures exist and have zero schema errors."""
    assert DEMO_FIXTURE_PATH.exists()
    assert REPRO_FIXTURE_PATH.exists()

    demo = load_demo_cert()
    repro = load_repro_cert()

    assert validate_certificate_schema(demo) == []
    assert validate_certificate_schema(repro) == []


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


def test_verify_good_reproduction() -> None:
    """Validate that the reproduction certificate passes all checks."""
    passed, check_lines, score_p_q, score_dec = verify_certificate(REPRO_FIXTURE_PATH)
    assert passed is True
    assert score_p_q == "1787146240596586469/1000000000000000000"
    assert score_dec == "1.7871462405965864690000000000000000000000"
    assert any("Claim type gating: OK (reproduction)" in line for line in check_lines)


def test_tamper_1_coordinate_changed() -> None:
    """Tamper 1: Changing one coordinate causes verification to fail on geometry."""
    cert = load_demo_cert()
    # Shift circle 0 center outside bounds
    cert["construction"]["centers"][0] = ["1/50", "1/10"]
    # Recompute certificate hash so hash check passes
    cert["certificate_sha256"] = compute_canonical_certificate_hash(cert)

    passed, check_lines, _, _ = verify_certificate(cert)
    assert passed is False
    assert any(
        "Verifier exact evaluation: FAILED: INVALID" in line for line in check_lines
    )


def test_tamper_2_claimed_score_changed() -> None:
    """Tamper 2: Changing claimed score causes score parity failure."""
    cert = load_demo_cert()
    # Actual construction is 38/15; 37/15 is irreducible
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
    # Set best_known value equal to claimed_score (margin = 0)
    cert["best_known"] = {
        "value": "38/15",
        "source_url": "https://example.com/baseline",
        "retrieved_date": "2026-10-18",
    }
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
        "Schema validation: FAILED: Missing required property: ['claimed_score']"
        in line
        for line in check_lines
    )


def test_tamper_9_unknown_field_added() -> None:
    """Tamper 9: Adding an unknown field causes schema validation failure."""
    cert = load_demo_cert()
    cert["extra_unauthorized_property"] = 12345

    passed, check_lines, _, _ = verify_certificate(cert)
    assert passed is False
    assert any(
        "Unexpected extra property: ['extra_unauthorized_property']" in line
        for line in check_lines
    )


def test_tamper_10_invalid_construction_with_recomputed_hash() -> None:
    """Tamper 10: Swapping in an invalid construction fails on geometric validity."""
    cert = load_demo_cert()
    # Non-positive radius
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
    # Create stub checker that returns VALID with wrong score
    stub_script = tmp_path / "stub_checker.py"
    stub_script.write_text("print('VALID 99/1')", encoding="utf-8")

    # Update verifier hash in certificate to match stub so hash check passes
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
    out_repro = tmp_path / "issued_repro.json"
    cert_repro = make_certificate(
        run_id="circle_packing_n26_2b4ce989",
        claim_type="reproduction",
        best_known_value="1787146240596586469/1000000000000000000",
        best_known_url="https://example.com/test",
        out_path=out_repro,
    )
    assert out_repro.exists()
    assert cert_repro["claim_type"] == "reproduction"
    assert verify_certificate(out_repro)[0] is True

    # Demonstration claim (best_known omitted)
    out_demo = tmp_path / "issued_demo.json"
    cert_demo = make_certificate(
        run_id="circle_packing_n26_2b4ce989",
        claim_type="demonstration",
        out_path=out_demo,
    )
    assert out_demo.exists()
    assert cert_demo["best_known"] is None
    assert verify_certificate(out_demo)[0] is True


def test_make_cert_record_positive_margin(tmp_path: Path) -> None:
    """Test issuing a record claim with a positive margin exceeding best_known."""
    out_record = tmp_path / "issued_record.json"
    # Baseline 1.5 is less than score ~1.787
    cert_record = make_certificate(
        run_id="circle_packing_n26_2b4ce989",
        claim_type="record",
        best_known_value="3/2",
        best_known_url="https://example.com/old_record",
        out_path=out_record,
    )
    assert out_record.exists()
    assert cert_record["claim_type"] == "record"
    assert verify_certificate(out_record)[0] is True


def test_make_cert_refuses_non_positive_margin(tmp_path: Path) -> None:
    """Test that make_certificate refuses record certificate if margin <= 0."""
    out_path = tmp_path / "unwritten_record.json"
    # Baseline 3.0 exceeds score ~1.787
    with pytest.raises(ValueError, match="Record claim refused: margin"):
        make_certificate(
            run_id="circle_packing_n26_2b4ce989",
            claim_type="record",
            best_known_value="3/1",
            best_known_url="https://example.com/impossible",
            out_path=out_path,
        )
    # File must NOT have been written
    assert not out_path.exists()


def test_make_cert_validation_errors(tmp_path: Path) -> None:
    """Test error handling in make_certificate for invalid inputs."""
    out_path = tmp_path / "should_not_exist.json"

    # Invalid claim type
    with pytest.raises(ValueError, match="Invalid claim_type"):
        make_certificate(
            run_id="circle_packing_n26_2b4ce989",
            claim_type="invalid_type",
            out_path=out_path,
        )

    # Missing run directory
    with pytest.raises(FileNotFoundError, match="Run directory not found"):
        make_certificate(
            run_id="nonexistent_run_12345",
            claim_type="demonstration",
            out_path=out_path,
        )

    # Reproduction missing best_known
    with pytest.raises(ValueError, match="Reproduction claim requires"):
        make_certificate(
            run_id="circle_packing_n26_2b4ce989",
            claim_type="reproduction",
            out_path=out_path,
        )

    # Record missing best_known
    with pytest.raises(ValueError, match="Record claim requires"):
        make_certificate(
            run_id="circle_packing_n26_2b4ce989",
            claim_type="record",
            out_path=out_path,
        )


def test_cli_verify_and_make_cert(
    tmp_path: Path, capsys: pytest.CaptureFixture
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
    out_cli = str(tmp_path / "cli_cert.json")
    args_mc = Args()
    args_mc.run_id = "circle_packing_n26_2b4ce989"
    args_mc.claim_type = "demonstration"
    args_mc.best_known_value = None
    args_mc.best_known_url = None
    args_mc.best_known_date = None
    args_mc.out = out_cli
    ret_mc = handle_make_cert_command(args_mc)
    captured_mc = capsys.readouterr().out
    assert ret_mc == 0
    assert "Certificate issued to" in captured_mc


def test_schema_validation_edge_cases() -> None:
    """Test detailed schema validation edge cases."""
    assert (
        "Certificate root must be a JSON object"
        in validate_certificate_schema("not_a_dict")[0]
    )

    cert = load_demo_cert()

    # Bad schema_version
    bad = copy.deepcopy(cert)
    bad["schema_version"] = "v1"
    assert any("Invalid schema_version" in e for e in validate_certificate_schema(bad))

    # Bad problem_id
    bad = copy.deepcopy(cert)
    bad["problem_id"] = ""
    assert any("Invalid problem_id" in e for e in validate_certificate_schema(bad))

    # Bad problem_spec_sha256
    bad = copy.deepcopy(cert)
    bad["problem_spec_sha256"] = "xyz"
    assert any(
        "Invalid problem_spec_sha256" in e for e in validate_certificate_schema(bad)
    )

    # Bad claim_type
    bad = copy.deepcopy(cert)
    bad["claim_type"] = "unsupported"
    assert any("Invalid claim_type" in e for e in validate_certificate_schema(bad))

    # Bad construction type
    bad = copy.deepcopy(cert)
    bad["construction"] = "not_obj"
    assert any("Invalid construction" in e for e in validate_certificate_schema(bad))

    # Bad construction keys
    bad = copy.deepcopy(cert)
    bad["construction"] = {"centers": []}
    assert any(
        "Construction object must contain exactly" in e
        for e in validate_certificate_schema(bad)
    )

    # Bad centers count
    bad = copy.deepcopy(cert)
    bad["construction"]["centers"] = bad["construction"]["centers"][:20]
    assert any(
        "centers must be a list of 26" in e for e in validate_certificate_schema(bad)
    )

    # Bad center element
    bad = copy.deepcopy(cert)
    bad["construction"]["centers"][0] = [1, 2]
    assert any(
        "must be a 2-element list of strings" in e
        for e in validate_certificate_schema(bad)
    )

    # Bad radii count
    bad = copy.deepcopy(cert)
    bad["construction"]["radii"] = bad["construction"]["radii"][:25]
    assert any(
        "radii must be a list of 26" in e for e in validate_certificate_schema(bad)
    )

    # Bad radius element
    bad = copy.deepcopy(cert)
    bad["construction"]["radii"][0] = 0.1
    assert any("must be a string" in e for e in validate_certificate_schema(bad))

    # Claimed score not in lowest terms
    bad = copy.deepcopy(cert)
    bad["claimed_score"] = "76/30"
    assert any("not in lowest terms" in e for e in validate_certificate_schema(bad))

    # Bad best_known type
    bad = copy.deepcopy(cert)
    bad["best_known"] = "not_dict"
    assert any(
        "best_known must be an object or null" in e
        for e in validate_certificate_schema(bad)
    )

    # Bad best_known date
    bad = copy.deepcopy(cert)
    bad["best_known"] = {
        "value": "1/2",
        "source_url": "http",
        "retrieved_date": "bad_date",
    }
    assert any(
        "retrieved_date must be an ISO 8601 date" in e
        for e in validate_certificate_schema(bad)
    )

    # Bad run type
    bad = copy.deepcopy(cert)
    bad["run"] = "not_dict"
    assert any(
        "run must be an object or null" in e for e in validate_certificate_schema(bad)
    )

    # Bad verifiers type
    bad = copy.deepcopy(cert)
    bad["verifiers"] = "not_dict"
    assert any(
        "verifiers must be an object" in e for e in validate_certificate_schema(bad)
    )

    # Bad certificate_sha256
    bad = copy.deepcopy(cert)
    bad["certificate_sha256"] = "short"
    assert any(
        "certificate_sha256 must be a 64-char hex string" in e
        for e in validate_certificate_schema(bad)
    )


def test_schema_load_function() -> None:
    """Test loading certificate schema directly from file."""
    schema = load_certificate_schema()
    assert isinstance(schema, dict)
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"


def test_verify_missing_verifier_files(tmp_path: Path) -> None:
    """Test verify_certificate failure when verifier files are missing."""
    cert = load_demo_cert()
    nonexistent = tmp_path / "nonexistent.py"

    # Missing exact verifier
    passed, check_lines, _, _ = verify_certificate(
        cert, exact_verifier_override=nonexistent
    )
    assert passed is False
    assert any(
        "Verifier SHA-256: FAILED: verifier_exact.py not found" in line
        for line in check_lines
    )

    # Missing independent verifier
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
    """Test demonstration and reproduction claim type gating rules."""
    # Demonstration with best_known not null
    cert_demo = load_demo_cert()
    cert_demo["best_known"] = {
        "value": "1/2",
        "source_url": "https://example.com",
        "retrieved_date": "2026-10-18",
    }
    cert_demo["certificate_sha256"] = compute_canonical_certificate_hash(cert_demo)
    passed, lines, _, _ = verify_certificate(cert_demo)
    assert passed is False
    assert any("Demonstration requires best_known null" in line for line in lines)

    # Reproduction with best_known is null
    cert_repro = load_demo_cert()
    cert_repro["claim_type"] = "reproduction"
    cert_repro["best_known"] = None
    cert_repro["certificate_sha256"] = compute_canonical_certificate_hash(cert_repro)
    passed, lines, _, _ = verify_certificate(cert_repro)
    assert passed is False
    assert any("Reproduction requires best_known" in line for line in lines)

    # Record with invalid best_known fraction
    cert_rec = load_demo_cert()
    cert_rec["claim_type"] = "record"
    cert_rec["best_known"] = {
        "value": "not_a_fraction",
        "source_url": "https://example.com",
        "retrieved_date": "2026-10-18",
    }
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
    assert any("Record claim requires best_known object" in line for line in lines)


def test_exact_verifier_exception_handling() -> None:
    """Test verify_certificate handling when exact verifier raises an exception."""
    cert = load_demo_cert()
    # "not_a_number" passes schema (string <= 100) but fails exact fraction parsing
    cert["construction"]["radii"][0] = "not_a_number"
    cert["certificate_sha256"] = compute_canonical_certificate_hash(cert)

    passed, lines, _, _ = verify_certificate(cert)
    assert passed is False
    assert any("Verifier exact evaluation: FAILED" in line for line in lines)


def test_make_cert_malformed_summary_json(tmp_path: Path) -> None:
    """Test make_certificate resilience when summary.json is unparseable."""
    out_cert = tmp_path / "cert_with_bad_summary.json"
    # Copy smoke run fixture directory
    real_run_dir = Path(__file__).parent.parent / "runs" / "circle_packing_n26_2b4ce989"
    run_copy = tmp_path / "run_copy"
    import shutil

    shutil.copytree(real_run_dir, run_copy)
    # Write invalid JSON into summary.json
    (run_copy / "summary.json").write_text("{broken json", encoding="utf-8")

    cert = make_certificate(
        run_id="run_copy",
        runs_dir=tmp_path,
        claim_type="demonstration",
        out_path=out_cert,
    )
    assert out_cert.exists()
    assert cert["run"]["iterations"] == 20  # fallback iteration count
    assert verify_certificate(out_cert)[0] is True


def test_schema_more_edge_cases() -> None:
    """Test additional detailed schema edge cases for 100% path coverage."""
    cert = load_demo_cert()

    # Center coordinate > 100 chars
    bad = copy.deepcopy(cert)
    bad["construction"]["centers"][0][0] = "1" * 101
    assert any(
        "exceeds length cap of 100" in e for e in validate_certificate_schema(bad)
    )

    # Radius > 100 chars
    bad = copy.deepcopy(cert)
    bad["construction"]["radii"][0] = "1" * 101
    assert any(
        "exceeds length cap of 100" in e for e in validate_certificate_schema(bad)
    )

    # best_known extra keys
    bad = copy.deepcopy(cert)
    bad["best_known"] = {
        "value": "1/2",
        "source_url": "http",
        "retrieved_date": "2026-10-18",
        "extra_key": "bad",
    }
    assert any("must contain exactly" in e for e in validate_certificate_schema(bad))

    # best_known non-string value
    bad["best_known"] = {
        "value": 123,
        "source_url": "http",
        "retrieved_date": "2026-10-18",
    }
    assert any(
        "best_known.value must be a string" in e
        for e in validate_certificate_schema(bad)
    )

    # best_known value > 100 chars
    bad["best_known"] = {
        "value": "1" * 101,
        "source_url": "http",
        "retrieved_date": "2026-10-18",
    }
    assert any(
        "best_known.value exceeds 100" in e for e in validate_certificate_schema(bad)
    )

    # best_known non-string source_url
    bad["best_known"] = {
        "value": "1/2",
        "source_url": 999,
        "retrieved_date": "2026-10-18",
    }
    assert any(
        "best_known.source_url must be a string" in e
        for e in validate_certificate_schema(bad)
    )

    # run extra keys
    bad = copy.deepcopy(cert)
    bad["run"] = {"extra": 1}
    assert any("run must contain" in e for e in validate_certificate_schema(bad))

    # run negative iterations
    bad_run = {
        "run_id": "r1",
        "engine": "openevolve",
        "engine_version": "1.0",
        "model": "m",
        "iterations": -5,
        "best_fast_score": "1.0",
        "shrink_loss_exact": "0/1",
    }
    bad["run"] = bad_run
    assert any(
        "iterations must be a non-negative" in e
        for e in validate_certificate_schema(bad)
    )

    # run non-string field
    bad_run["iterations"] = 10
    bad_run["run_id"] = 123  # type: ignore[assignment]
    bad["run"] = bad_run
    assert any(
        "run.run_id must be a string" in e for e in validate_certificate_schema(bad)
    )

    # verifiers extra keys
    bad = copy.deepcopy(cert)
    bad["verifiers"] = {
        "exact_sha256": "a" * 64,
        "independent_sha256": "b" * 64,
        "extra": "x",
    }
    assert any("verifiers must contain" in e for e in validate_certificate_schema(bad))

    # verifiers non-64 hex
    bad["verifiers"] = {
        "exact_sha256": "invalid_hex",
        "independent_sha256": "b" * 64,
    }
    assert any(
        "verifiers.exact_sha256 must be a 64-char hex string" in e
        for e in validate_certificate_schema(bad)
    )

    bad["verifiers"] = {
        "exact_sha256": "a" * 64,
        "independent_sha256": "invalid_hex",
    }
    assert any(
        "verifiers.independent_sha256 must be a 64-char hex string" in e
        for e in validate_certificate_schema(bad)
    )

    # created_at empty
    bad = copy.deepcopy(cert)
    bad["created_at"] = ""
    assert any(
        "created_at must be an ISO 8601 string" in e
        for e in validate_certificate_schema(bad)
    )


def test_make_cert_from_construction_file(tmp_path: Path) -> None:
    """Test generating certificate directly from construction JSON."""
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
