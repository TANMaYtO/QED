"""Tests for the engine runner wrapper using a mocked evolution loop."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openevolve.api import EvolutionResult

from qed.engine.run import compute_config_hash, run_problem


@pytest.mark.asyncio
async def test_compute_config_hash(tmp_path: Path) -> None:
    """Verify SHA-256 computation on configuration content."""
    cfg_file = tmp_path / "test_config.yaml"
    cfg_file.write_text("max_iterations: 10\n", encoding="utf-8")

    hash_val = await compute_config_hash(cfg_file)
    assert isinstance(hash_val, str)
    assert len(hash_val) == 64


@pytest.mark.asyncio
async def test_run_problem_with_mocked_evolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify run_problem creates runs/<run_id>/summary.json with expected schema."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-mock-key")

    fake_program = MagicMock()
    fake_program.metrics = {"sum_radii": 0.9634}

    fake_result = EvolutionResult(
        best_program=fake_program,
        best_score=0.9634,
        best_code="# mock evolved code",
        metrics={"token_usage": {"prompt_tokens": 120, "completion_tokens": 80}},
        output_dir=str(tmp_path / "openevolve_out"),
    )

    mock_run = AsyncMock(return_value=fake_result)
    mock_resolve = AsyncMock(return_value="gemini-2.5-flash")
    with (
        patch("qed.engine.run._run_evolution_async", new=mock_run),
        patch("qed.engine.run.resolve_flash_model", new=mock_resolve),
    ):
        summary: dict[str, Any] = await run_problem(
            problem_id="circle_packing_n26",
            iterations=5,
            run_id="test_run_001",
            output_root=tmp_path / "runs",
        )

    assert summary["problem_id"] == "circle_packing_n26"
    assert summary["run_id"] == "test_run_001"
    assert summary["iterations"] == 5
    assert summary["llm_calls"] == 5
    assert summary["best_fast_score"] == 0.9634
    assert summary["wall_time"] >= 0.0
    assert summary["token_counts"] == {
        "prompt_tokens": 120,
        "completion_tokens": 80,
        "reasoning_tokens": 0,
        "total_tokens": 200,
    }
    assert summary["estimated_cost"] is None

    summary_file: Path = tmp_path / "runs" / "test_run_001" / "summary.json"
    assert summary_file.is_file()

    loaded_summary = json.loads(summary_file.read_text(encoding="utf-8"))
    assert loaded_summary["problem_id"] == "circle_packing_n26"
    assert loaded_summary["config_hash"] == summary["config_hash"]
    # Check that secrets are not included in summary.json
    assert "api_key" not in loaded_summary
    assert "GEMINI_API_KEY" not in loaded_summary
