PY := uv run python

.PHONY: test eval eval-snapshot eval-record eval-live fixtures

test:
	$(PY) -m pytest -q

# CI target: replays recorded model responses, needs no API key.
# Writes outputs/eval-replay.json and leaves the tracked snapshot alone.
eval:
	$(PY) -m evals.run_evals --mode replay

# Refresh the published snapshot evals/results.json from the recordings.
eval-snapshot:
	$(PY) -m evals.run_evals --mode replay --out evals/results.json

# Re-record after changing the prompt, the schema, or the fixtures.
eval-record:
	$(PY) -m evals.run_evals --mode record

# Live run against the API without touching the recordings.
eval-live:
	$(PY) -m evals.run_evals --mode live

fixtures:
	$(PY) -m evals.make_fixtures
