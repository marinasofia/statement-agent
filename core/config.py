"""Runtime configuration.

Every path is anchored to the project root, never to the current working
directory, so the pipeline behaves the same from a cron job, a container,
or a test runner started in another folder. Environment variables override
the defaults; .env is loaded once here and never overrides variables that
were already set by the process environment.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env", override=False)


def _path_from_env(var: str, default: Path) -> str:
    value = os.getenv(var)
    return str(Path(value).expanduser().resolve()) if value else str(default)


# --- LLM ---
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
CLAUDE_MAX_TOKENS = 4096          # High enough for statements with many transactions
CLAUDE_MAX_RETRIES = 3            # How many times to retry a failed API call
CLAUDE_RETRY_MIN_WAIT = 2         # Seconds before first retry
CLAUDE_RETRY_MAX_WAIT = 10        # Max seconds between retries

# --- File Validation ---
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "20"))
ALLOWED_UPLOAD_DIR = _path_from_env("UPLOAD_DIR", PROJECT_ROOT / "uploads")

# --- Output ---
EXCEL_OUTPUT_PATH = _path_from_env("EXCEL_OUTPUT_PATH", PROJECT_ROOT / "outputs" / "statements_batch.xlsx")
