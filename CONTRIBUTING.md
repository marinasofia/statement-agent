# Contributing

Follow the [Code of Conduct](CODE_OF_CONDUCT.md). Report vulnerabilities through
[SECURITY.md](SECURITY.md), and use synthetic PDFs for public bug reports.

## Setup and checks

Use Python 3.12 or newer and the checkout setup in [README.md](README.md).
The following checks run offline and require no API key:

```bash
.venv/bin/python -m pytest -q
mkdir -p outputs
.venv/bin/python -m evals.run_evals --mode replay --out outputs/eval-replay.json
```

The repository's Makefile assumes `.venv/bin/python`. `make test` runs tests;
`make eval` writes the tracked `evals/results.json`, so inspect that diff before
committing. `make eval-live` and `make eval-record` make paid API requests;
record mode replaces cassettes. Run them only when intentionally updating the
model evaluation, then record model/prompt/schema versions and compare outcomes.
Dependencies are declared in `pyproject.toml`; an environment lock is pending.

## Debugging and changes

Use `.venv/bin/python -m pytest tests/test_reconcile.py -q` to isolate arithmetic
checks. Use `--pdb -x` on a failing test to inspect synthetic state. Patch model
calls in unit tests. Do not put real statements, credentials, or identifying
logs into fixtures. `--verbose` on the live runner prints account details.

Keep extraction, schema validation, reconciliation, and workbook output
responsibilities separate. Include a regression test and updated documentation
with each behavior change. Describe meaningful changes under `Unreleased` in
[CHANGELOG.md](CHANGELOG.md). Keep PRs focused, use type annotations on new
interfaces, and avoid em and en dashes in text, comments, and commit messages.

The roadmap and actual GitHub checks are in [docs/maintenance.md](docs/maintenance.md).
Do not claim a lint, type, coverage, or security gate before it exists.
