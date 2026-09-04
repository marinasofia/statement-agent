# Bank Statement Extraction Agent

Turns PDF bank statements into a reconciled Excel workbook. Built for the situation where statements arrive from many banks in inconsistent layouts, someone has to key the balances into a spreadsheet, and a wrong number costs more than a slow one.

The model extracts data; deterministic checks then compare balances, transactions,
and dates when the statement provides enough information. A skipped check is
not proof of correctness, and the current status model does not distinguish
every unverified case. Review the output before using it for reconciliation.

[![CI](https://github.com/marinasofia/statement-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/marinasofia/statement-agent/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-0.2.0-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

## Quickstart without an API key

Requires Python 3.12 or newer. Commands use a POSIX shell and run from the checkout.
The replay exercises synthetic statements and recorded model responses.

```bash
git clone https://github.com/marinasofia/statement-agent.git
cd statement-agent
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
mkdir -p outputs
.venv/bin/python -m evals.run_evals --mode replay --out outputs/eval-replay.json
.venv/bin/python -m pytest -q
```

Expect 11 passing replay cases. Replay costs and timings come from recordings,
not new API calls or a benchmark of your computer. An installed wheel currently
omits required configuration, so use this source-checkout setup.


## What to look at first

- `agents/statement_extraction/reconcile.py`: the deterministic check. Opening balance plus the sum of transactions must equal the closing balance to the cent, and transaction dates must fall inside the statement period. There is no model call in this file.
- `evals/`: eleven synthetic statements with expected values, including a prompt injection case, a 260-transaction statement, and an image-only PDF. Current numbers are in the table below, and CI re-runs the suite on every pull request without an API key.
- `node_validate_file` in `agents/statement_extraction/nodes.py`: path containment is checked before existence, so the error message cannot be used to probe the host filesystem. A test proves the two messages are identical.

## Results on the eval set

Recorded 2026-09-03 with Haiku 4.5 as the first-pass model and Sonnet 5 as the escalation model. Ten text statements plus one image-only PDF.

| Metric | Result |
|---|---|
| Cases passed | 11 / 11 |
| Closing balance exact match | 10 / 10 |
| Opening balance exact match | 9 / 9 (one fixture prints none) |
| Account number, account holder, currency, statement date | 10 / 10 each |
| Transaction count and transaction sum | 10 / 10 |
| Reconciled on the first Haiku call | 10 / 10, zero escalations |
| Injection case: output unchanged | yes |
| Image-only PDF rejected before any model call | yes |
| Duplicate statement detected by the workbook | yes |
| Median cost per statement | $0.0025 |
| 260-transaction statement | $0.041, 36 s, reconciled to the cent |
| Median latency per statement | 1.7 s |
| Whole suite | $0.063 |

Reproduce offline with `make eval` (replays recorded responses, no key needed) or live with `make eval-live`. Full per-case output is in `evals/results.json`.

Escalation has not yet been exercised by a fixture, because Haiku reconciled every one on the first attempt. The path is covered by unit tests with a fake API, not by a recorded live case. That is a gap in the fixture set, not a claim about production traffic.

## Architecture

Where deterministic code ends and the model begins:

```
validate_file    deterministic   extension, containment, size
extract_text     deterministic   pdfplumber, unicode sanitisation, input cap
detect_format    deterministic   signature match against formats_library
extract_fields   MODEL           structured output, schema enforced by the API
reconcile        deterministic   arithmetic, period, dates in period
escalate         MODEL           only if reconcile fails; stronger model, once
finalize         deterministic   statement month from the validated date
```

The model is called at most twice per statement, three times if a first attempt fails semantic validation. It returns a JSON object whose shape is enforced by the API (structured outputs), so there is no JSON cleanup and no repair prompt. If the response is truncated (`stop_reason` is `max_tokens`) the job fails with `TRUNCATED_OUTPUT` rather than passing a partial object downstream.

Why there is no "ask the model to fix its JSON" step: a repair prompt that sees only the broken output and the error will satisfy the schema by inventing the missing value. Schema-valid is not the same as true. The one retry that exists re-runs extraction from the source text with the validation error appended, and it only fires on semantic failures the API cannot enforce, such as an ambiguous date.

Dates: the prompt asks for ISO 8601 and the validator normalises month-name forms to ISO. Numeric forms with slashes or dots are rejected rather than guessed, because 03/04/2026 is two different dates depending on the bank's country. The retry with the error attached is what turns a rejected date into a corrected one.

## Failure modes

| Situation | Behaviour | Code |
|---|---|---|
| Not a PDF, outside `uploads/`, over the size limit | rejected before any read | `NOT_PDF`, `OUTSIDE_UPLOAD_DIR`, `TOO_LARGE` |
| Image-only PDF | rejected; OCR is out of scope | `SCANNED` |
| Text above the input cap | rejected, not truncated silently | `INPUT_TOO_LARGE` |
| Model output cut off | job fails | `TRUNCATED_OUTPUT` |
| Model declines the document | job fails | `MODEL_REFUSED` |
| Semantic validation fails after one retry | job fails | `SCHEMA_INVALID` |
| Balances do not reconcile after escalation | written to the "Needs review" sheet with the delta and reasons | status `NEEDS_REVIEW` |
| Escalation itself errors | first extraction kept, row goes to review with the escalation error as a reason | status `NEEDS_REVIEW` |
| Same account, statement date and closing balance already in the workbook | skipped and counted | status `DUPLICATE` |
| API 429, 5xx, or connection error | SDK retries with backoff, then fails | `API_ERROR` |

The batch runner records status, error code, accepted model, tokens, estimated cost, latency, and reconciliation delta in a JSONL job report after workbook output. Failed workbook writes can currently prevent that report. Logs and reports may include filenames, reconciliation amounts, and error context; treat them as sensitive. The batch summary prints status counts, estimated spend, and latency statistics.

## Cost and model choice

Haiku 4.5 does the first pass because a statement is a reading task, not a reasoning task. On the eval set it costs a median of $0.0025 per statement at roughly 1,500 tokens in and 200 out; the 260-row statement costs $0.041. Sonnet 5 is used only when reconciliation fails on the Haiku output. Escalations are logged per job, so the share of statements that needed the stronger model is a number in the run summary rather than a guess. On the current fixtures that share is zero.

## Security and data handling

**Path traversal.** File paths are resolved to real paths and checked for containment in the upload directory before existence is tested. Errors never echo the supplied path.

**Untrusted content.** Document text and model output are untrusted. Structured output and the injection fixture test specific behaviors; they do not guarantee safe spreadsheet output or correctness for arbitrary documents. Keep use limited to trusted evaluation inputs until the output contracts and deployment controls have been reviewed. See [SECURITY.md](SECURITY.md).

**Invisible characters.** Zero-width and bidirectional control characters are stripped before the text reaches the model or the spreadsheet.

**PII.** Statement text, including names and account numbers, is sent to the Anthropic API. Logs and run records can include identifying filenames, amounts, and error context; `--verbose` also prints per-file account details. Account numbers could be masked deterministically before the call and restored from the regex match afterwards. That is not built, because whether it is needed depends on the customer's data agreement, and it should be decided there rather than assumed here.

## Multi-client configuration

`formats_library/` holds format definitions: fields, detection signatures, and output columns. `clients/<id>/overrides/` holds per-client changes that deep-merge over the base, so an override only states what differs. `CLIENT_ID` is read once at boot and validated against the folders that exist on disk. The `default` format has no signatures and acts as the fallback; a new bank layout is a yaml with signatures, and `detect_format` picks the entry with the most matches that meets its `min_matches`.

## Setup and usage

After the offline quickstart, copy `.env.example` to `.env` and set a valid
`ANTHROPIC_API_KEY` for an explicitly authorized live run. Place only documents
you are permitted to send to Anthropic in `uploads/`. Live evaluation and
recording also send fixture text and incur charges.

```bash
cp .env.example .env
mkdir -p uploads outputs
# Edit .env and put authorized text-based PDF statements in uploads/ first.
.venv/bin/python run_batch.py --input uploads/ --output outputs/aug.xlsx --workers 3
```

For another input directory, set `UPLOAD_DIR` before starting Python as well
as `--input`; file validation uses the configured upload root. Keep an output
directory component, such as `outputs/report.xlsx`, until bare-filename support
is fixed. `--month` is only a fallback when the extracted date provides no month.

Environment variables: `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `ESCALATION_MODEL`
(empty disables escalation), `CLAUDE_MAX_TOKENS`, `MAX_INPUT_CHARS`,
`MAX_FILE_SIZE_MB`, `UPLOAD_DIR`, `EXCEL_OUTPUT_PATH`, and `CLIENT_ID`.
Defaults are in [`.env.example`](.env.example) and [core/config.py](core/config.py).
Relative environment paths resolve against the process working directory;
unset defaults are anchored to the project. Model availability depends on the
provider account. No API key is needed for the replay quickstart or tests.

## Out of scope, on purpose

OCR for scanned statements. Formats beyond the ones in `formats_library`. A web interface. Each would add surface area without changing the core question, which is whether the numbers can be trusted.

## Stack

Python 3.12, LangGraph, Anthropic SDK with structured outputs, Pydantic v2, pdfplumber, openpyxl, pytest, reportlab for fixtures.


## Development and status

MVP for controlled batch evaluation. CI runs tests and replay evaluations;
coverage, lint, and static-type gates are not yet enforced. Phase 0 measured
81.7% line-plus-branch coverage across the application, including its CLI.

TODO: complete the [package, failure-path, and CI follow-up](https://github.com/marinasofia/statement-agent/issues/8).
See [CONTRIBUTING.md](CONTRIBUTING.md) for development and debugging,
[maintainer guidance](docs/maintenance.md) for branch rules,
[CHANGELOG.md](CHANGELOG.md), and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

[MIT](LICENSE). Synthetic fixtures are for testing, not real account records.
