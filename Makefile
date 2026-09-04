PY := .venv/bin/python

.PHONY: test eval eval-record eval-live fixtures

test:
	$(PY) -m pytest -q

# CI target: replays recorded model responses, needs no API key.
eval:
	$(PY) -m evals.run_evals --mode replay

# Re-record after changing the prompt, the schema, or the fixtures.
eval-record:
	$(PY) -m evals.run_evals --mode record

# Live run against the API without touching the recordings.
eval-live:
	$(PY) -m evals.run_evals --mode live

fixtures:
	$(PY) -m evals.make_fixtures
