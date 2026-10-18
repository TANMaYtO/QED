# QED

QED is an evolutionary discovery engine for open mathematics and algorithm problems.
It drives an LLM-guided optimization loop to propose candidate constructions and algorithms.
A rigorous, non-floating-point trust layer verifies every solution exactly before any claim is accepted.

## Status

**Phase 0**: Scaffolding and environment setup.

## Claims Policy

A result may be designated as a **record** only if all of the following conditions hold:

1. **Exact Verification**: It passes verification by the exact verifier and an independent checker, both computed using exact arithmetic (`fractions.Fraction` or integers).
2. **Sourced Benchmark**: The best-known baseline value is documented with a canonical source URL and retrieval date.
3. **Strict Improvement**: It beats the baseline value by an exact margin strictly greater than zero.
4. **Reproducibility**: The evolutionary run is fully reproducible from this repository.
5. **Published Certificate**: A signed/verifiable certificate file is published and passes `qed verify`.

Until a verified certificate is published, any result is characterized as *attempted* or *reproduced*, never *discovered*.

## Development

Install the package in editable mode with development dependencies:

```bash
pip install -e .[dev]
```

Run test suite and linter:

```bash
pytest -q
ruff check .
```

Verify the CLI:

```bash
qed --version
```
