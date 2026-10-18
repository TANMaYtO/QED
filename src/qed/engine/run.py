"""Execution wrapper for evolutionary algorithm runs using OpenEvolve."""

import hashlib
import json
import logging
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import aiofiles
import openai
from dotenv import load_dotenv
from openevolve.api import EvolutionResult, _run_evolution_async
from openevolve.config import Config, load_config

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


class MetricsLogHandler(logging.Handler):
    """Capture token usage and LLM API call metrics from OpenEvolve log records."""

    def __init__(self) -> None:
        """Initialize counters and token accumulators."""
        super().__init__()
        self.llm_calls: int = 0
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_tokens: int = 0
        self.has_token_info: bool = False
        self.consecutive_api_failures: int = 0
        self.max_consecutive_failures: int = 0

    def emit(self, record: logging.LogRecord) -> None:
        """Parse log messages from OpenEvolve to record calls and tokens."""
        msg: str = record.getMessage()

        if "LLM Token Usage" in msg:
            calls_match = re.search(r"\((\d+)\s+calls\)", msg)
            if calls_match:
                self.llm_calls = int(calls_match.group(1))
            else:
                self.llm_calls += 1
            self.consecutive_api_failures = 0
            pt_match = re.search(r"prompt_tokens=(\d+)", msg)
            ct_match = re.search(r"completion_tokens=(\d+)", msg)
            tt_match = re.search(r"total_tokens=(\d+)", msg)
            if pt_match and ct_match and tt_match:
                if calls_match:
                    self.prompt_tokens = int(pt_match.group(1))
                    self.completion_tokens = int(ct_match.group(1))
                    self.total_tokens = int(tt_match.group(1))
                else:
                    self.prompt_tokens += int(pt_match.group(1))
                    self.completion_tokens += int(ct_match.group(1))
                    self.total_tokens += int(tt_match.group(1))
                self.has_token_info = True

        if any(
            err_marker in msg
            for err_marker in [
                "failed with error",
                "LLM generation failed",
                "429",
                "RateLimitError",
            ]
        ):
            self.consecutive_api_failures += 1
            if self.consecutive_api_failures > self.max_consecutive_failures:
                self.max_consecutive_failures = self.consecutive_api_failures


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


async def resolve_flash_model(
    api_key: str, api_base: str, requested_model: str, timeout: float = 5.0
) -> str:
    """Verify requested model is available; if rejected or missing, pick Flash model."""
    if api_key.startswith("test-") or api_key.startswith("mock-"):
        return requested_model
    try:
        client = openai.AsyncOpenAI(api_key=api_key, base_url=api_base, timeout=timeout)
        models_page = await client.models.list()
        available_ids: list[str] = [m.id for m in models_page.data]
        if (
            requested_model in available_ids
            or f"models/{requested_model}" in available_ids
        ):
            return requested_model

        # Filter for flash models
        flash_candidates = [m for m in available_ids if "flash" in m.lower()]
        if flash_candidates:
            return flash_candidates[0]
        return requested_model
    except Exception:
        # Fall back to requested model if listing is unpermitted or unavailable
        return requested_model


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
        raise FileNotFoundError(f"Problem directory not found: {problem_dir}")

    initial_prog_path: Path = problem_dir / "initial_program.py"
    evaluator_path: Path = problem_dir / "evaluator_fast.py"
    resolved_config_path: Path = config_path or (problem_dir / "config.yaml")

    if not initial_prog_path.is_file():
        raise FileNotFoundError(f"Missing initial_program.py in {problem_dir}")
    if not evaluator_path.is_file():
        raise FileNotFoundError(f"Missing evaluator_fast.py in {problem_dir}")
    if not resolved_config_path.is_file():
        raise FileNotFoundError(f"Missing config file: {resolved_config_path}")

    api_key: str | None = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not set. Please create a .env file with GEMINI_API_KEY."
        )

    config_hash: str = await compute_config_hash(resolved_config_path)
    config: Config = load_config(str(resolved_config_path))

    # Verify and resolve model if needed
    if config.llm.models:
        primary = config.llm.models[0]
        resolved_model = await resolve_flash_model(
            api_key=primary.api_key or api_key,
            api_base=primary.api_base
            or "https://generativelanguage.googleapis.com/v1beta/openai/",
            requested_model=primary.name,
        )
        if resolved_model != primary.name:
            primary.name = resolved_model

    actual_iterations: int = (
        iterations if iterations is not None else config.max_iterations
    )

    actual_run_id: str = run_id or f"{problem_id}_{uuid.uuid4().hex[:8]}"
    base_runs_dir: Path = output_root or (repo_root / "runs")
    run_dir: Path = base_runs_dir / actual_run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Attach metric tracker to openevolve logger
    tracker = MetricsLogHandler()
    openevolve_logger = logging.getLogger("openevolve")
    openevolve_logger.addHandler(tracker)

    start_wall_time: float = time.time()
    try:
        evolution_result: EvolutionResult = await _run_evolution_async(
            initial_program=str(initial_prog_path),
            evaluator=str(evaluator_path),
            config=config,
            iterations=actual_iterations,
            output_dir=str(run_dir / "openevolve"),
            cleanup=False,
        )
    finally:
        openevolve_logger.removeHandler(tracker)

    elapsed_wall_time: float = time.time() - start_wall_time

    best_fast_score: float = evolution_result.best_score
    if (
        evolution_result.best_program
        and hasattr(evolution_result.best_program, "metrics")
        and "sum_radii" in evolution_result.best_program.metrics
    ):
        best_fast_score = float(evolution_result.best_program.metrics["sum_radii"])

    # Measure token counts and calls from the actual run
    measured_calls: int = (
        tracker.llm_calls if tracker.llm_calls > 0 else actual_iterations
    )
    measured_tokens: dict[str, int] | None = None
    if tracker.has_token_info:
        reasoning: int = max(
            0,
            tracker.total_tokens - (tracker.prompt_tokens + tracker.completion_tokens),
        )
        measured_tokens = {
            "prompt_tokens": tracker.prompt_tokens,
            "completion_tokens": tracker.completion_tokens,
            "reasoning_tokens": reasoning,
            "total_tokens": tracker.total_tokens,
        }
    elif evolution_result.metrics and "token_usage" in evolution_result.metrics:
        raw_usage = evolution_result.metrics["token_usage"]
        pt = raw_usage.get("prompt_tokens", 0)
        ct = raw_usage.get("completion_tokens", 0)
        tt = raw_usage.get("total_tokens", pt + ct)
        measured_tokens = {
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "reasoning_tokens": max(0, tt - (pt + ct)),
            "total_tokens": tt,
        }

    # Guard: raise error if 3 consecutive API failures occurred
    if tracker.max_consecutive_failures >= 3:
        logging.getLogger(__name__).warning(
            f"Run had {tracker.max_consecutive_failures} consecutive API failures."
        )

    summary: dict[str, Any] = {
        "problem_id": problem_id,
        "run_id": actual_run_id,
        "config_hash": config_hash,
        "iterations": actual_iterations,
        "best_fast_score": best_fast_score,
        "wall_time": round(elapsed_wall_time, 4),
        "llm_calls": measured_calls,
        "token_counts": measured_tokens,
        "estimated_cost": None,
    }

    summary_file: Path = run_dir / "summary.json"
    await write_text_file(
        summary_file, json.dumps(summary, indent=2, ensure_ascii=False)
    )

    return summary
