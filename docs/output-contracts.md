# Output contracts

The writer stores all newly appended strings as text, including `=`, `+`, `-`,
`@`, and spreadsheet error tokens. It preserves the original string rather than
adding an apostrophe. It rejects nonfinite numeric cells and incompatible
existing worksheet headers. Existing workbook formulas are not rewritten or
sanitized. Use a trusted workbook as the append target.

Semantic statement validation rejects nonfinite and boolean balances and
transaction amounts. Provider-facing draft schemas stay unchanged; semantic
checks run after extraction. Monetary arithmetic still uses floats with the
configured reconciliation tolerance, not an exact decimal ledger.

A workbook is saved to a temporary file in the destination directory and then
replaced with `os.replace`. A failed save or replacement preserves the prior
file and removes the temporary file. Bare output filenames work. An empty or
all-failed batch writes a Run summary sheet if there are no statement sheets.
Once statement sheets exist, the placeholder summary is removed.

The batch CLI attempts a separate, uniquely named JSONL run log even if workbook
export fails. Its summary records `output_status` and, on failure, a generic
`output_error_code`. No output can be recovered if its storage is unwritable;
the CLI returns 1 when extraction, workbook export, or run-log output fails.
An empty input directory is a successful no-op and does not create output.

Atomic replacement prevents partial files. It does not make the workbook and
log one transaction, provide crash durability via fsync, or coordinate concurrent
writers. Run one batch writer per target. The log contains private extraction
evidence and needs the same access controls as the source statements.

TODO: installed-package configuration, exact monetary arithmetic, durable batch
recovery, and CI enforcement remain tracked in [issue 8](https://github.com/marinasofia/statement-agent/issues/8).
