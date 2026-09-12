# Bank Statement Extraction Agent

Extract PDF bank statements into Excel, check balances and dates, and route exceptions through a local review workflow.

[![CI](https://github.com/marinasofia/statement-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/marinasofia/statement-agent/actions/workflows/ci.yml)

[Review walkthrough](docs/review-workflow.md) · [Evaluation results](evals/results.json) · [Technical reference](docs/technical-reference.md)

## How it works

```text
PDF → text extraction → structured model output → reconciliation → review → Excel
```

Claude extracts fields. Deterministic code checks balances, transaction dates and statement periods when the source provides the required values. Failed reconciliation can trigger one escalation to a stronger model. The local review workflow supports corrections, approval history and retryable exports.

Automated checks and human approval are separate states. Missing source values can leave checks unverified, so review the output before using it for financial reconciliation.

## Try it without an API key

Python 3.12 or newer, from a source checkout.

```sh
git clone https://github.com/marinasofia/statement-agent.git
cd statement-agent
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
mkdir -p outputs
.venv/bin/python -m evals.run_evals --mode replay --out outputs/eval-replay.json
.venv/bin/python -m pytest -q
```

The replay covers 11 synthetic fixtures, including a long statement, duplicate input, prompt injection and an image-only PDF. Costs and timings in the recorded results describe the original calls, not the replay. Recorded fixtures do not exercise escalation, which is covered separately by unit tests.

## Engineering details

- Structured extraction with Pydantic validation and bounded semantic retries
- Balance reconciliation, date checks and duplicate handling
- Spreadsheet formula protection and upload-path containment
- Per-file status, token usage, estimated cost and latency records
- Atomic workbook replacement and failure reporting

Start with [reconciliation](agents/statement_extraction/reconcile.py), the [output contracts](docs/output-contracts.md) and the [review tests](tests/test_review.py).

## Scope

Text-based PDFs, local batch processing and local review. OCR and a hosted multi-user service are outside the current implementation. Use the source checkout because installed wheels do not yet include required configuration.

Live extraction sends statement text to Anthropic and incurs API charges. Configuration, data handling, model choices and recorded measurements are documented in the [technical reference](docs/technical-reference.md).

Python · LangGraph · Anthropic SDK · Pydantic · pdfplumber · openpyxl

[Development](CONTRIBUTING.md) · [Security](SECURITY.md) · [MIT license](LICENSE)
