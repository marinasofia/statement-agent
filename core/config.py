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
CLAUDE_MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "16384"))   # A long statement can run to hundreds of transactions
CLAUDE_MAX_RETRIES = 3            # SDK retries for 429, 5xx and connection errors
# When the cheap model's numbers do not reconcile, one more attempt on a
# stronger model. Set ESCALATION_MODEL to an empty string to disable.
ESCALATION_MODEL = os.getenv("ESCALATION_MODEL", "claude-sonnet-5")
# Character cap on the text sent to the model. The 20MB file limit says
# nothing about token count; a text-heavy PDF can exceed the context window.
MAX_INPUT_CHARS = int(os.getenv("MAX_INPUT_CHARS", "300000"))

# --- File Validation ---
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "20"))
ALLOWED_UPLOAD_DIR = _path_from_env("UPLOAD_DIR", PROJECT_ROOT / "uploads")

# --- Output ---
EXCEL_OUTPUT_PATH = _path_from_env("EXCEL_OUTPUT_PATH", PROJECT_ROOT / "outputs" / "statements_batch.xlsx")
