import os
from dotenv import load_dotenv

load_dotenv()

# --- LLM ---
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
CLAUDE_MAX_TOKENS = 4096          # High enough for statements with many transactions
CLAUDE_MAX_RETRIES = 3            # How many times to retry a failed API call
CLAUDE_RETRY_MIN_WAIT = 2         # Seconds before first retry
CLAUDE_RETRY_MAX_WAIT = 10        # Max seconds between retries

# --- File Validation ---
MAX_FILE_SIZE_MB = 20
ALLOWED_UPLOAD_DIR = os.path.abspath("uploads")

# --- Output ---
EXCEL_OUTPUT_PATH = "outputs/statements_batch.xlsx"