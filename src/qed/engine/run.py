"""Execution wrapper for evolutionary algorithm runs using OpenEvolve."""

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

import aiofiles
from dotenv import load_dotenv
from openevolve.api import EvolutionResult, _run_evolution_async
from openevolve.config import Config, load_config


async def read_text_file(path: Path) -> str:
    """Read and return entire content of a text file asynchronously."""
    async with aiofiles.open(path, encoding="utf-8") as file_handle:
        return await file_handle.read()


async def write_text_file(path: Path, content: str) -> None:
    """Write text content to a destination path asynchronously."""
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(path, mode="w", encoding="utf-8") as file_handle:
        await file_handle.write(content)


async def compute_config_hash(config_path: Path) -> str:
    """Compute and return the SHA-256 hex digest of a configuration file."""
    raw_content: str = await read_text_file(config_path)
    return hashlib.sha256(raw_content.encode("utf-8")).hexdigest()


async def run_problem(
    problem_id: str,
    iterations: int | None = None,
    config_path: Path | None = None,
    run_id: str | None = None,
    output_root: Path | None = None,
) -> dict[str, Any]:
    """Execute OpenEvolve for a problem and generate a summary report.

    Args:
        problem_id: Directory name under src/qed/problems.
        iterations: Number of evolution iterations to run.
        config_path: Optional path to YAML configuration.
        run_id: Optional explicit identifier for the run.
        output_root: Base path for run outputs.

    Returns:
        Dictionary holding summary metrics.
    """
    load_dotenv()

    repo_root: Path = Path(__file__).resolve().parent.parent.parent.parent
    problem_dir: Path = repo_root / "src" / "qed" / "problems" / problem_id
    if not problem_dir.is_dir():
        raise FileNotFoundError(
            f"Problem directory not found: {problem_dir}"
        )

    initial_prog_path: Path = problem_dir / "initial_program.py"
    evaluator_path: Path = problem_dir / "evaluator_fast.py"
    resolved_config_path: Path = config_path or (problem_dir / "config.yaml")

    if not initial_prog_path.is_file():
        raise FileNotFoundError(f"Missing initial_program.py in {problem_dir}")
    if not evaluator_path.is_file():
        raise FileNotFoundError(f"Missing evaluator_fast.py in {problem_dir}")
    if not resolved_config_path.is_file():
        raise FileNotFoundError(f"Missing config file: {resolved_config_path}")

    config_hash: str = await compute_config_hash(resolved_config_path)
    config: Config = load_config(str(resolved_config_path))

    actual_iterations: int = (
        iterations if iterations is not None else config.max_iterations
    )

    actual_run_id: str = run_id or f"{problem_id}_{uuid.uuid4().hex[:8]}"
    base_runs_dir: Path = output_root or (repo_root / "runs")
    run_dir: Path = base_runs_dir / actual_run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    start_wall_time: float = time.time()

    evolution_result: EvolutionResult = await _run_evolution_async(
        initial_program=str(initial_prog_path),
        evaluator=str(evaluator_path),
        config=config,
        iterations=actual_iterations,
        output_dir=str(run_dir / "openevolve"),
        cleanup=False,
    )

    elapsed_wall_time: float = time.time() - start_wall_time

    best_fast_score: float = evolution_result.best_score
    if (
        evolution_result.best_program
        and hasattr(evolution_result.best_program, "metrics")
        and "sum_radii" in evolution_result.best_program.metrics
    ):
        best_fast_score = float(
            evolution_result.best_program.metrics["sum_radii"]
        )

    token_counts: dict[str, int] | None = None
    if evolution_result.metrics and "token_usage" in evolution_result.metrics:
        token_counts = evolution_result.metrics["token_usage"]

    estimated_cost: float | None = None
    if evolution_result.metrics and "estimated_cost" in evolution_result.metrics:
        estimated_cost = float(evolution_result.metrics["estimated_cost"])

    summary: dict[str, Any] = {
        "problem_id": problem_id,
        "run_id": actual_run_id,
        "config_hash": config_hash,
        "iterations": actual_iterations,
        "best_fast_score": best_fast_score,
        "wall_time": round(elapsed_wall_time, 4),
        "llm_calls": actual_iterations,
        "token_counts": token_counts,
        "estimated_cost": estimated_cost,
    }

    summary_file: Path = run_dir / "summary.json"
    await write_text_file(
        summary_file, json.dumps(summary, indent=2, ensure_ascii=False)
    )

    return summary
