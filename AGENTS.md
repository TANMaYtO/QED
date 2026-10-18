# AGENTS.md - rules for every coding agent working on QED

Project: QED is a discovery engine. An LLM-driven evolutionary loop proposes constructions for open math/algorithm problems; a trust layer verifies them exactly. Trust is the product.

Hard rules
1. Honesty: never invent results, scores, costs, or citations. Every number you report must come from a command you ran; paste the command and its real output. If something failed, say so plainly.
2. Exactness: any score that gates a claim is computed with exact arithmetic (fractions.Fraction or integers). Floats are allowed only in the fast in-loop evaluator and must never gate a promotion or a claim.
3. Never read, copy, or paraphrase code from any private or employer project. Build from the problem spec and public sources only; credit open-source code you adapt (license and attribution in the file header).
4. Secrets: API keys live in .env (gitignored). Never print or commit them.
5. Cost: before any run that calls an LLM API more than 50 times, print the estimated number of calls and stop for confirmation. Respect QED_MAX_USD if set.
6. Tests first: every module ships with pytest tests. Run pytest -q and ruff check . before declaring done.
7. Small commits with clear messages. Do not rewrite history.
8. If the spec is ambiguous, stop and ask. Do not guess silently.
9. Do not add dependencies without stating why.
10. Final report format: What I did / Commands run (with real output) / Files changed / What I am unsure about / Suggested next step.
