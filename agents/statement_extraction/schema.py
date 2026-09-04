from enum import StrEnum
from datetime import datetime
from typing import List, Optional, TypedDict

from pydantic import BaseModel, field_validator


class Status(StrEnum):
    OK = "OK"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ErrorCode(StrEnum):
    """Machine-readable reason a job stopped. `error` carries the human text."""
    NO_FILE_PATH = "NO_FILE_PATH"
    NOT_PDF = "NOT_PDF"
    OUTSIDE_UPLOAD_DIR = "OUTSIDE_UPLOAD_DIR"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    TOO_LARGE = "TOO_LARGE"
    PDF_READ_FAILED = "PDF_READ_FAILED"
    SCANNED = "SCANNED"
    FORMAT_LIBRARY_ERROR = "FORMAT_LIBRARY_ERROR"
    INPUT_TOO_LARGE = "INPUT_TOO_LARGE"
    TRUNCATED_OUTPUT = "TRUNCATED_OUTPUT"
    MODEL_REFUSED = "MODEL_REFUSED"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    API_ERROR = "API_ERROR"


# Dates the model may return. ISO first because the prompt asks for it.
# Numeric day/month/year forms with slashes or dots are deliberately not
# accepted: 03/04/2025 is two different dates depending on the bank's
# country, and guessing silently is worse than asking the model again.
_ACCEPTED_DATE_FORMATS = ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y")


def normalise_date(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    for fmt in _ACCEPTED_DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(
        f"Unrecognised or ambiguous date '{value}'. Dates must be ISO 8601 (YYYY-MM-DD)."
    )


class TransactionDraft(BaseModel):
    date: Optional[str] = None
    description: str
    amount: float


class StatementDraft(BaseModel):
    """The shape requested from the model. Schema only, no semantic checks,
    because the API enforces this shape and semantic failures need a retry
    that sees the source text."""
    account_holder: str
    closing_balance: float
    opening_balance: Optional[float] = None
    account_number: Optional[str] = None
    statement_date: Optional[str] = None
    statement_period_start: Optional[str] = None
    statement_period_end: Optional[str] = None
    currency: Optional[str] = None
    bank_name: Optional[str] = None
    transactions: Optional[List[TransactionDraft]] = None


class Transaction(TransactionDraft):
    @field_validator("date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        return normalise_date(v)


class StatementData(StatementDraft):
    """Validated statement. Dates are normalised to ISO on the way through."""
    transactions: Optional[List[Transaction]] = None

    @field_validator("statement_date", "statement_period_start", "statement_period_end")
    @classmethod
    def validate_dates(cls, v: Optional[str]) -> Optional[str]:
        return normalise_date(v)

    @field_validator("currency")
    @classmethod
    def normalise_currency(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        if len(v) != 3 or not v.isalpha():
            raise ValueError(f"currency must be a 3-letter ISO 4217 code, got '{v}'")
        return v


class AgentState(TypedDict, total=False):
    file_path: str
    job_id: str
    client_id: str
    format_id: str        # chosen by detect_format from the format library
    raw_text: str
    validated_data: dict  # StatementData as a dict, dates normalised
    statement_month: str  # YYYY-MM, derived from statement_date
    reconciliation: dict  # ReconciliationResult.as_dict()
    status: str           # "OK" or "NEEDS_REVIEW" once reconciled
    review_reasons: list  # failed checks, human-readable
    escalated: bool       # a stronger model was tried after reconciliation failed
    escalation_error: str # why the stronger model's attempt failed, if it did
    llm_calls: list       # one usage dict per model call
    error: str            # human-readable reason the job stopped
    error_code: str       # ErrorCode value
