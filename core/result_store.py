"""Extraction results saved the moment each one finishes, keyed by the file's SHA-256.

Model calls are the slow, paid step that cannot be repeated for free. Saving each
result as it completes means a crash loses at most the jobs that were in flight, and
rerunning the same folder pays only for files that never finished. The key is the
file's bytes, not its name, so a renamed copy is still recognised and an edited file
is extracted again.

Failed results are not kept, so a rerun retries them. The extracted statement text
is dropped before saving: the workbook does not need it, and it is the most sensitive
field. The database file is created readable by its owner only.
"""

import hashlib
import json
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

NOT_STORED = ("raw_text",)


def file_identity(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ResultStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            os.close(os.open(self.path, os.O_CREAT | os.O_WRONLY, 0o600))
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS results ("
                "identity TEXT PRIMARY KEY, saved_at REAL NOT NULL, state TEXT NOT NULL)"
            )

    def get(self, identity: str):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("SELECT state FROM results WHERE identity = ?", (identity,)).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, identity: str, state: dict) -> bool:
        """Keep a finished extraction. Returns False for failures, which are not kept."""
        if state.get("error"):
            return False
        kept = {k: v for k, v in state.items() if k not in NOT_STORED}
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(
                "INSERT OR REPLACE INTO results (identity, saved_at, state) VALUES (?, ?, ?)",
                (identity, time.time(), json.dumps(kept, allow_nan=False)),
            )
        return True
