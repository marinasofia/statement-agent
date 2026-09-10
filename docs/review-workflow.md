# Local statement review

The review queue is a single-operator CLI with a read-only HTML preview. It runs locally. It has no web server, accounts or remote collaboration. The existing batch export is retained for compatibility and is not human-approved output. Use `--review-db` to opt into approval before export.

## Synthetic walkthrough, no API calls

From the checkout after installing the README dependencies:

```bash
.venv/bin/python demo_review.py
```

Open `outputs/demo-review.html`. It presents source text, original extraction, current values, checks and audit history. Compare with `evals/fixtures/clean_usd/statement.pdf`; the source text is extracted text, not a visual proof of every PDF field. The demo starts in `NEEDS_REVIEW` even if arithmetic passes.

Copy the printed item ID into `ITEM` below. The queue retains it across restarts.

```bash
ITEM=replace_with_printed_id
.venv/bin/python review.py --db outputs/demo-review.sqlite show "$ITEM"
```

To correct a value, save the complete `current` object from `show` as `outputs/correction.json`, edit the relevant fields, then submit it with the displayed revision:

```bash
.venv/bin/python review.py --db outputs/demo-review.sqlite correct "$ITEM" \
  --revision 0 --reviewer Marina --reason 'Compared the name with the PDF' \
  --data outputs/correction.json
```

A correction increments the revision and requires approval again. The original extraction remains available. Reload with `show` before each edit to avoid approving stale values.

```bash
.venv/bin/python review.py --db outputs/demo-review.sqlite approve "$ITEM" \
  --revision 1 --reviewer Marina --reason 'Compared every field and transaction with the PDF'
.venv/bin/python review.py --db outputs/demo-review.sqlite export "$ITEM"
```

If no correction was made, approve revision 0 instead. Failed checks block approval. Skipped checks require `--acknowledge-skipped` and a reason explaining the independent review. An acknowledgement records a human decision; it does not convert an unperformed check into a passed check.

The exported workbook includes the summary, transaction rows and approval history. Filenames include the PDF content hash and approved revision. They contain sensitive data if the inputs do. Repeated export recreates the same revision artifact; edits require a new approval and produce a new revision filename. Earlier artifacts remain historical snapshots and are not revoked or deleted automatically.

Regenerate the preview after edits:

```bash
.venv/bin/python review.py --db outputs/demo-review.sqlite preview "$ITEM" \
  --output outputs/demo-review.html
```

## Existing batch integration

For an already authorized live extraction, append `--review-db outputs/review.sqlite` to the normal batch command. This persists each completed extraction before proceeding and does not write the legacy workbook. Successful saved PDFs are skipped on restart using a SHA-256 content key. Failed extractions can be attempted again, with their previous error retained in history. Do not perform a live run without permission to send those documents to the provider.

The standalone `import-result` command accepts a full extraction-state JSON and its source PDF. It is a trusted operator interface: it cannot prove that the supplied extraction came from that PDF. Prefer the integrated batch path or synthetic demo.

## Failure and recovery

- Interrupted between files: rerun with the same database. Completed successful items retain corrections and approvals. An extraction interrupted before its SQLite commit may run again and incur another model call in live mode.
- Stale edit: reload the item and apply the intended change to the current revision.
- Invalid correction: validation rolls back the transaction and leaves the revision unchanged.
- Failed export: approval remains saved and an `EXPORT_FAILED` event records the error class. Fix disk access or choose another output directory, then rerun export without model calls.
- Interrupted export: the destination is replaced only after the full workbook is built. If the process ends after replacement but before the database commit, retry export to reconcile the history. Filesystem and database updates are not one distributed transaction.
- Database unavailable or corrupt: stop and restore a known backup. Do not delete it to force a rerun. This is a local SQLite store, not a tamper-resistant audit service.

Reviewer names are self-entered, not authenticated identities. The database, previews and workbooks are not encrypted by this application. Store them in an appropriately protected local location. Failed extraction cannot be manually approved. Multi-user hosting, OCR and financial actions remain outside this implementation.

## Manual acceptance checklist

1. Run the synthetic demo and inspect both PDF and preview.
2. Introduce an incorrect closing balance. Verify approval is blocked.
3. Restore the correct value and approve the current revision.
4. Export and inspect the Transactions and Approval history sheets.
5. Restart the CLI and verify the original, correction and approval remain.
6. Try a stale revision and an unwritable export location; verify neither loses the decision.

No user trial or time-saving result is claimed. A tester still needs to complete this walkthrough and report where it is unclear.
